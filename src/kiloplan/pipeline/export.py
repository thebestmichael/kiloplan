"""Exports the app database's tables to Parquet, one file per table.

Run with: uv run python -m kiloplan.pipeline.export
These files are the raw layer the dbt project reads. Account tables (users, login
sessions) are never exported.
"""

import argparse
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine

from kiloplan.storage.db import get_engine

DEFAULT_LAKE = "data/lake/raw"

RAW_TABLES = (
    "lifters",
    "uploads",
    "blocks",
    "weeks",
    "program_rows",
    "foods",
    "diary_entries",
)


def lake_path() -> Path:
    return Path(os.environ.get("KILOPLAN_LAKE_PATH", DEFAULT_LAKE))


def export_tables(engine: Engine, destination: Path) -> dict[str, int]:
    """Write each raw table to `<destination>/<table>.parquet`. Returns rows per table."""
    destination.mkdir(parents=True, exist_ok=True)
    counts = {}
    with engine.connect() as connection:
        for table in RAW_TABLES:
            frame = pd.read_sql_table(table, connection)
            frame.to_parquet(destination / f"{table}.parquet", index=False)
            counts[table] = len(frame)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=lake_path(), help="folder to write to")
    arguments = parser.parse_args()
    for table, rows in export_tables(get_engine(), arguments.out).items():
        print(f"{table}: {rows} rows")
    print(f"Wrote {len(RAW_TABLES)} tables to {arguments.out}")


if __name__ == "__main__":
    main()
