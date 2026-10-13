"""Read access to the tables dbt builds (the marts). DuckDB locally."""

import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

DEFAULT_WAREHOUSE = "data/warehouse.duckdb"

Row = dict[str, Any]


class Warehouse:
    """The built summary tables. They are only as fresh as the last pipeline run."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("KILOPLAN_WAREHOUSE_PATH", DEFAULT_WAREHOUSE))

    @property
    def available(self) -> bool:
        return self.path.exists()

    @property
    def built_at(self) -> datetime | None:
        """When the pipeline last wrote the warehouse."""
        if not self.available:
            return None
        return datetime.fromtimestamp(self.path.stat().st_mtime, tz=UTC)

    def _query(self, sql: str, parameters: list[Any]) -> list[Row]:
        with duckdb.connect(str(self.path), read_only=True) as connection:
            cursor = connection.execute(sql, parameters)
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, values, strict=True)) for values in cursor.fetchall()]

    def weekly_volume(self, lifter_id: int, lift: str, weeks: int) -> list[Row]:
        """The lifter's most recent weeks of one lift, newest first."""
        return self._query(
            """
            select block_index, week_number, week_start, total_sets, total_reps, volume_kg,
                   top_load_kg
            from fct_weekly_volume
            where lifter_id = ? and lift = ?
            order by week_sequence desc
            limit ?
            """,
            [lifter_id, lift, weeks],
        )

    def daily_macros(self, lifter_id: int, first_day: date, last_day: date) -> list[Row]:
        """The lifter's logged days in a date range, newest first."""
        return self._query(
            """
            select diary_date, kcal, protein_g, carbs_g, fat_g, entries
            from fct_daily_macros
            where lifter_id = ? and diary_date between ? and ?
            order by diary_date desc
            """,
            [lifter_id, first_day, last_day],
        )
