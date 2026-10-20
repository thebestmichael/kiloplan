"""Loads the Parquet files in S3 into Snowflake tables, for dbt's Snowflake target to read.

Each table is dropped and rebuilt from the files, so a load always matches the last export.
Connection settings come from SNOWFLAKE_* environment variables (kept in .env). The login
is a key pair, so no password exists; the private key stays on this machine, outside the repo.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

if TYPE_CHECKING:
    from snowflake.connector import SnowflakeConnection

RAW_SCHEMA = "RAW"
STAGE = "KILOPLAN_LAKE"


def snowflake_type(arrow_type: pa.DataType) -> str:
    if pa.types.is_boolean(arrow_type):
        return "BOOLEAN"
    if pa.types.is_integer(arrow_type):
        return "NUMBER(38, 0)"
    if pa.types.is_floating(arrow_type):
        return "FLOAT"
    if pa.types.is_timestamp(arrow_type):
        return "TIMESTAMP_NTZ"
    if pa.types.is_date(arrow_type):
        return "DATE"
    if pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type):
        return "ARRAY"
    return "VARCHAR"


def create_table_sql(table: str, schema: pa.Schema) -> str:
    """Columns are left unquoted so Snowflake upper-cases them and dbt's SQL finds them."""
    columns = ",\n    ".join(f"{field.name} {snowflake_type(field.type)}" for field in schema)
    return f"create or replace table {RAW_SCHEMA}.{table} (\n    {columns}\n)"


def create_stage_sql(bucket: str, prefix: str) -> str:
    return (
        f"create or replace stage {RAW_SCHEMA}.{STAGE}\n"
        f"url = 's3://{bucket}/{prefix}/'\n"
        "credentials = (aws_key_id = %(key_id)s aws_secret_key = %(secret_key)s)\n"
        "file_format = (type = parquet)"
    )


def copy_sql(table: str) -> str:
    return (
        f"copy into {RAW_SCHEMA}.{table} from @{RAW_SCHEMA}.{STAGE}/{table}.parquet\n"
        "match_by_column_name = case_insensitive"
    )


def connect() -> "SnowflakeConnection":
    import snowflake.connector

    key_path = Path(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"]).expanduser()
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key_file=str(key_path),
        role=os.environ.get("SNOWFLAKE_ROLE", "KILOPLAN_PIPELINE"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "KILOPLAN_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "KILOPLAN"),
    )


def load_lake(
    connection: "SnowflakeConnection", lake: Path, bucket: str, prefix: str, tables: tuple[str, ...]
) -> dict[str, int]:
    """Rebuild `raw.<table>` from `s3://bucket/prefix/<table>.parquet`. Returns rows per table."""
    cursor = connection.cursor()
    cursor.execute(f"create schema if not exists {RAW_SCHEMA}")
    cursor.execute(
        create_stage_sql(bucket, prefix),
        {
            "key_id": os.environ["AWS_ACCESS_KEY_ID"],
            "secret_key": os.environ["AWS_SECRET_ACCESS_KEY"],
        },
    )
    counts = {}
    for table in tables:
        schema = pq.read_schema(lake / f"{table}.parquet")
        cursor.execute(create_table_sql(table, schema))
        cursor.execute(copy_sql(table))
        cursor.execute(f"select count(*) from {RAW_SCHEMA}.{table}")
        counts[table] = cursor.fetchone()[0]
    return counts
