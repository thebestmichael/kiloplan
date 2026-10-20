"""The Snowflake loader's SQL and call order, against a recording stand-in for the connection."""

from pathlib import Path

import pandas as pd
import pyarrow as pa

from kiloplan.pipeline.snowflake_load import copy_sql, create_stage_sql, create_table_sql, load_lake


class RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.parameters: list[dict | None] = []

    def cursor(self) -> "RecordingConnection":
        return self

    def execute(self, sql: str, parameters: dict | None = None) -> None:
        self.statements.append(sql)
        self.parameters.append(parameters)

    def fetchone(self) -> tuple[int]:
        return (3,)


def test_table_columns_are_unquoted_and_typed():
    schema = pa.schema(
        [
            ("id", pa.int64()),
            ("name", pa.large_string()),
            ("kcal", pa.float64()),
            ("rpe_below_5", pa.bool_()),
            ("day", pa.timestamp("ms")),
            ("skipped_sheets", pa.list_(pa.string())),
            ("lifter_id", pa.null()),
        ]
    )
    assert create_table_sql("foods", schema) == (
        "create or replace table RAW.foods (\n"
        "    id NUMBER(38, 0),\n"
        "    name VARCHAR,\n"
        "    kcal FLOAT,\n"
        "    rpe_below_5 BOOLEAN,\n"
        "    day TIMESTAMP_NTZ,\n"
        "    skipped_sheets ARRAY,\n"
        "    lifter_id VARCHAR\n"
        ")"
    )


def test_stage_points_at_the_bucket_without_putting_keys_in_the_sql():
    sql = create_stage_sql("my-bucket", "raw")
    assert "url = 's3://my-bucket/raw/'" in sql
    assert "%(key_id)s" in sql and "%(secret_key)s" in sql


def test_copy_matches_columns_by_name():
    assert copy_sql("weeks") == (
        "copy into RAW.weeks from @RAW.KILOPLAN_LAKE/weeks.parquet\n"
        "match_by_column_name = case_insensitive"
    )


def test_load_rebuilds_each_table_in_order(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "key-id")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    pd.DataFrame({"id": [1, 2, 3]}).to_parquet(tmp_path / "weeks.parquet", index=False)
    connection = RecordingConnection()

    counts = load_lake(connection, tmp_path, "my-bucket", "raw", ("weeks",))

    assert counts == {"weeks": 3}
    kinds = [statement.split("\n")[0].split(" (")[0] for statement in connection.statements]
    assert kinds == [
        "create schema if not exists RAW",
        "create or replace stage RAW.KILOPLAN_LAKE",
        "create or replace table RAW.weeks",
        "copy into RAW.weeks from @RAW.KILOPLAN_LAKE/weeks.parquet",
        "select count(*) from RAW.weeks",
    ]
    assert connection.parameters[1] == {"key_id": "key-id", "secret_key": "secret"}
