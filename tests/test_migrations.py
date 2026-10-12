from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from kiloplan.storage.db import connect, migrate
from kiloplan.storage.models import Base, Lifter, PerformedSet

# what `create_all` made before migrations existed
BASELINE_TABLES = ("lifters", "uploads", "blocks", "weeks", "program_rows", "notes", "issues")


def schema_differences(engine):
    with engine.connect() as connection:
        return compare_metadata(MigrationContext.configure(connection), Base.metadata)


def test_migrations_build_the_same_schema_as_the_models(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    migrate(url)
    assert schema_differences(connect(url)) == []


def test_migrating_twice_changes_nothing(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    migrate(url)
    migrate(url)
    assert schema_differences(connect(url)) == []


def test_a_database_made_before_migrations_is_adopted_with_its_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    engine = connect(url)
    Base.metadata.create_all(
        engine, tables=[Base.metadata.tables[name] for name in BASELINE_TABLES]
    )
    with Session(engine) as session:
        session.add(Lifter(name="default"))
        session.commit()
    assert "alembic_version" not in inspect(engine).get_table_names()

    migrate(url)

    engine = connect(url)
    assert "alembic_version" in inspect(engine).get_table_names()
    with Session(engine) as session:
        assert session.scalars(select(Lifter.name)).all() == ["default"]
    assert schema_differences(engine) == []


def test_programs_stored_before_performed_sets_are_copied_into_them(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    migrate(url, "0001")
    engine = connect(url)
    row = (
        "INSERT INTO program_rows (id, week_id, day_label, day_order, row_order, movement_raw, "
        "lift, variation, sets, reps, reps_raw, load_kg, load_raw, assumed_kg, rpe, rpe_below_5, "
        "intensity_raw, target_load_raw, sheet_cell) VALUES "
        "({id}, 1, 'Day 1', 0, {id}, 'Squat', 'squat', 'competition', 1, 3, '3', {load}, '', 0, "
        "{rpe}, 0, '', '', 'J5')"
    )
    with engine.begin() as connection:
        for statement in (
            "INSERT INTO lifters (id, name) VALUES (7, 'ana')",
            "INSERT INTO uploads (id, lifter_id, filename, uploaded_at, skipped_sheets) "
            "VALUES (1, 7, 'program.xlsx', '2026-03-30 00:00:00', '[]')",
            "INSERT INTO blocks (id, upload_id, sheet_name, block_index) "
            "VALUES (1, 1, 'Spring', 0)",
            "INSERT INTO weeks (id, block_id, week_number, label, start_date, sequence) "
            "VALUES (1, 1, 4, 'Week 4', '2026-03-23', 0)",
            row.format(id=1, load=183.7, rpe=9),
            row.format(id=2, load="NULL", rpe="NULL"),
        ):
            connection.execute(text(statement))

    migrate(url)

    with Session(connect(url)) as session:
        copied = session.scalars(select(PerformedSet)).one()
        assert (copied.lifter_id, copied.program_row_id, copied.source) == (7, 1, "coach_sheet")
        assert (copied.performed_on.isoformat(), copied.date_precision) == ("2026-03-23", "week")
        assert (copied.lift, copied.reps, copied.load_kg, copied.rpe) == ("squat", 3, 183.7, 9.0)
