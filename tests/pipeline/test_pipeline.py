"""Builds the dbt project on a small program and checks its tables against the Python formulas."""

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from sqlalchemy.orm import Session

from kiloplan.analytics.e1rm import e1rm_from_rpe
from kiloplan.analytics.nutrition import Macros
from kiloplan.analytics.volume import weekly_volume
from kiloplan.ingestion.coach_sheet import parse_workbook
from kiloplan.pipeline.export import RAW_TABLES, export_tables
from kiloplan.storage import nutrition_store
from kiloplan.storage.db import create_db_engine
from kiloplan.storage.models import Food, ProgramRow
from kiloplan.storage.program_store import get_or_create_lifter, store_program
from kiloplan.storage.warehouse import Warehouse
from workbooks import EXAMPLE_PROGRAM, as_bytes, program_workbook


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The example program and two days of food, exported and run through dbt once."""
    tmp_path = tmp_path_factory.mktemp("pipeline")
    engine = create_db_engine(f"sqlite:///{tmp_path / 'app.db'}")
    session = Session(engine)
    result = parse_workbook(as_bytes(program_workbook(EXAMPLE_PROGRAM)))
    store_program(session, "ana", "program.xlsx", result)
    lifter = get_or_create_lifter(session, "ana")
    rice = Food(
        source="usda", fdc_id=1, name="Rice", kcal=130, protein_g=2.7, carbs_g=28, fat_g=0.3
    )
    session.add(rice)
    session.flush()
    nutrition_store.log_food(session, lifter, date(2026, 10, 12), "lunch", rice, 200)
    nutrition_store.log_food(session, lifter, date(2026, 10, 12), "dinner", rice, 100)
    nutrition_store.quick_add(
        session, lifter, date(2026, 10, 13), "snacks", "Bar", Macros(200, 20, 22, 7)
    )
    session.commit()

    lake, warehouse = tmp_path / "lake", tmp_path / "warehouse.duckdb"
    counts = export_tables(engine, lake)
    environment = {
        **os.environ,
        "KILOPLAN_LAKE_PATH": str(lake),
        "KILOPLAN_WAREHOUSE_PATH": str(warehouse),
    }
    # dbt runs as its own process, as it does in real use, so it releases the warehouse file
    target = tmp_path / "target"
    run = subprocess.run(
        [
            str(Path(sys.executable).parent / "dbt"),
            "build",
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt",
            "--target-path",
            str(target),
            "--log-path",
            str(tmp_path / "logs"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )
    results = json.loads((target / "run_results.json").read_text())["results"]
    return {
        "run": run,
        "results": results,
        "counts": counts,
        "lake": lake,
        "warehouse": warehouse,
        "lifter": lifter.id,
        "session": session,
    }


def query(built, sql):
    with duckdb.connect(str(built["warehouse"]), read_only=True) as connection:
        return connection.execute(sql).fetchall()


def test_export_writes_every_raw_table_and_no_account_data(built):
    assert set(built["counts"]) == set(RAW_TABLES)
    assert sorted(path.stem for path in built["lake"].glob("*.parquet")) == sorted(RAW_TABLES)
    assert "users" not in RAW_TABLES
    assert "auth_sessions" not in RAW_TABLES
    assert (
        len(pd.read_parquet(built["lake"] / "program_rows.parquet"))
        == built["counts"]["program_rows"]
    )


def test_dbt_builds_and_every_data_test_passes(built):
    assert built["run"].returncode == 0, built["run"].stdout[-2000:]
    results = built["results"]
    assert {result["status"] for result in results} <= {"success", "pass"}
    assert sum(result["unique_id"].startswith("model.") for result in results) == 8
    assert sum(result["unique_id"].startswith("test.") for result in results) >= 20


def test_weekly_volume_table_matches_the_python_metric(built):
    rows = [
        row
        for row in built["session"].query(ProgramRow)
        if row.lift != "other" and row.load_kg and row.sets and row.reps
    ]
    expected = weekly_volume(
        (row.week.sequence, row.lift, row.sets, row.reps, row.load_kg) for row in rows
    )
    actual = {
        (sequence, lift): volume
        for sequence, lift, volume in query(
            built, "select week_sequence, lift, volume_kg from fct_weekly_volume"
        )
    }
    assert actual.keys() == expected.keys()
    for key, volume in expected.items():
        assert actual[key] == pytest.approx(volume)
    # week 4 squat, every variation: 1x3 at 405, 3x5 at 365, paused 2x3 at 365,
    # 1x5 at 370 and 1x5 at 380 lb
    week_4_squat_lb = 1 * 3 * 405 + 3 * 5 * 365 + 2 * 3 * 365 + 5 * 370 + 5 * 380
    assert actual[1, "squat"] == pytest.approx(week_4_squat_lb * 0.45359237)


def test_e1rm_in_sql_matches_the_python_formula(built):
    computed = dict(
        query(
            built, "select program_row_id, e1rm_kg from int_training_sets where e1rm_kg is not null"
        )
    )
    with_rpe = [
        row
        for row in built["session"].query(ProgramRow)
        if row.lift != "other" and row.load_kg and row.reps and row.rpe is not None
    ]
    assert len(with_rpe) == len(computed) > 0
    for row in with_rpe:
        assert computed[row.id] == pytest.approx(e1rm_from_rpe(row.load_kg, row.reps, row.rpe))

    # the best squat of week 4: 380 lb x 5 at RPE 7, the Epley side of the formula is not hit
    best = query(
        built,
        "select best_e1rm_kg from fct_weekly_e1rm "
        "where lift = 'squat' and variation = 'competition' and week_number = 4",
    )
    assert best[0][0] == pytest.approx(380 * 0.45359237 * 36 / 29)


def test_sets_logged_below_rpe_5_have_no_e1rm(built):
    # week 1 of the new block has one squat, logged as "<5"
    rows = query(built, "select e1rm_kg, volume_kg from int_training_sets where week_number = 1")
    assert rows == [(None, pytest.approx(1 * 2 * 315 * 0.45359237))]


def test_daily_macros_table(built):
    days = query(
        built,
        "select diary_date, kcal, protein_g, carbs_g, fat_g, entries from fct_daily_macros "
        "order by diary_date",
    )
    assert days == [
        (
            date(2026, 10, 12),
            pytest.approx(390),
            pytest.approx(8.1),
            pytest.approx(84),
            pytest.approx(0.9),
            2,
        ),
        (date(2026, 10, 13), 200, 20, 22, 7, 1),
    ]


def test_warehouse_reader(built):
    warehouse = Warehouse(built["warehouse"])
    assert warehouse.available
    assert warehouse.built_at is not None

    squat = warehouse.weekly_volume(built["lifter"], "squat", weeks=2)
    assert [(week["block_index"], week["week_number"]) for week in squat] == [(1, 1), (0, 4)]
    assert squat[1]["top_load_kg"] == pytest.approx(405 * 0.45359237)
    assert warehouse.weekly_volume(built["lifter"], "squat", weeks=1)[0]["week_number"] == 1
    assert warehouse.weekly_volume(999, "squat", weeks=4) == []

    macros = warehouse.daily_macros(built["lifter"], date(2026, 10, 13), date(2026, 10, 13))
    assert [(day["diary_date"], day["kcal"]) for day in macros] == [(date(2026, 10, 13), 200)]
    both = warehouse.daily_macros(built["lifter"], date(2026, 10, 1), date(2026, 10, 31))
    assert [day["diary_date"].day for day in both] == [13, 12]


def test_a_missing_warehouse_is_reported_as_unavailable(tmp_path):
    warehouse = Warehouse(tmp_path / "nothing.duckdb")
    assert not warehouse.available
    assert warehouse.built_at is None
