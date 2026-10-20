"""Runs the whole pipeline: export the app database to Parquet, then build the dbt models.

Run from the repo root with: uv run python -m kiloplan.pipeline
Add `--target snowflake` to also load the files from S3 into Snowflake and build the models
there. That needs KILOPLAN_S3_BUCKET and the SNOWFLAKE_* settings in .env.
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from kiloplan.pipeline.export import RAW_TABLES, export_tables, lake_path
from kiloplan.pipeline.s3 import DEFAULT_PREFIX, bucket_name, upload_lake
from kiloplan.storage.db import get_engine

DBT_PROJECT = "dbt"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=("dev", "snowflake"), default="dev")
    target = parser.parse_args(argv).target

    load_dotenv()
    key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if key_path:
        # dbt does not expand `~`, so hand it an absolute path
        os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"] = str(Path(key_path).expanduser())
    try:
        from dbt.cli.main import dbtRunner
    except ImportError:
        print("dbt is not installed. Run `uv sync` to install the dev dependencies.")
        return 1

    destination = lake_path()
    counts = export_tables(get_engine(), destination)
    print(f"Exported {sum(counts.values())} rows from {len(counts)} tables to {destination}")

    bucket = bucket_name()
    if bucket:
        keys = upload_lake(destination, bucket)
        print(f"Uploaded {len(keys)} files to s3://{bucket}/")

    if target == "snowflake":
        if not bucket:
            print("Set KILOPLAN_S3_BUCKET: Snowflake loads the files from S3.")
            return 1
        from kiloplan.pipeline.snowflake_load import connect, load_lake

        connection = connect()
        try:
            loaded = load_lake(connection, destination, bucket, DEFAULT_PREFIX, RAW_TABLES)
        finally:
            connection.close()
        print(f"Loaded {sum(loaded.values())} rows into Snowflake raw tables")

    result = dbtRunner().invoke(
        [
            "build",
            "--project-dir",
            DBT_PROJECT,
            "--profiles-dir",
            DBT_PROJECT,
            "--target",
            target,
        ]
    )
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
