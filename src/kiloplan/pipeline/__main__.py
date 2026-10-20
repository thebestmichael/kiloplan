"""Runs the whole pipeline: export the app database to Parquet, then build the dbt models.

Run from the repo root with: uv run python -m kiloplan.pipeline
"""

import sys

from dotenv import load_dotenv

from kiloplan.pipeline.export import export_tables, lake_path
from kiloplan.pipeline.s3 import bucket_name, upload_lake
from kiloplan.storage.db import get_engine

DBT_PROJECT = "dbt"


def main() -> int:
    load_dotenv()
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

    result = dbtRunner().invoke(
        ["build", "--project-dir", DBT_PROJECT, "--profiles-dir", DBT_PROJECT]
    )
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
