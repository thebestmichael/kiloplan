"""Tools the assistant calls to look up a lifter's logged sets and to calculate loads.

Every number in an answer must come from one of these results, so each tool decides
its own `status` in code and returns loads in both kg and lb, already rounded for
display.
"""

import inspect
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from kiloplan.analytics.e1rm import (
    CHART_MIN_RPE,
    MAX_RPE,
    below_chart_range,
    e1rm_from_rpe,
    weight_for_rpe,
)
from kiloplan.ingestion.lifts import COMPETITION
from kiloplan.storage.models import Block, Lifter, NutritionGoal, ProgramRow, Upload, Week
from kiloplan.storage.program_store import latest_upload
from kiloplan.storage.warehouse import Warehouse

KG_PER_LB = 0.45359237
MAIN_LIFTS = ("squat", "bench", "deadlift")
# a stated load matches a logged one within this share of the logged load
LOAD_TOLERANCE = 0.01
MAX_LISTED_SETS = 8
MAX_REPORT_WEEKS = 12
MAX_REPORT_DAYS = 31

BELOW_CHART_NOTE = (
    f"RPE below {CHART_MIN_RPE:g} is under the usual RPE chart range, so this number is an "
    "extrapolation from reps in reserve and is less reliable."
)
FORMULA_NOTE = (
    "reps in reserve = 10 - RPE; hybrid formula (Brzycki up to 10 theoretical reps, Epley above)"
)

Result = dict[str, Any]


def _to_kg(load: float, unit: str) -> float:
    if unit not in ("kg", "lb"):
        raise ValueError(f"unit must be 'kg' or 'lb', got {unit!r}")
    return load * KG_PER_LB if unit == "lb" else load


def _loads(prefix: str, kg: float) -> Result:
    return {f"{prefix}_kg": round(kg, 1), f"{prefix}_lb": round(kg / KG_PER_LB, 1)}


def _show(kg: float) -> str:
    return f"{kg / KG_PER_LB:.1f} lb ({kg:.1f} kg)"


def _rpe_text(row: ProgramRow) -> str:
    if row.rpe_below_5:
        return "<5"
    return "not logged" if row.rpe is None else f"{row.rpe:g}"


def describe_set(row: ProgramRow) -> Result:
    """A logged set as the assistant sees it."""
    week, block = row.week, row.week.block
    where = f"block {block.block_index + 1}, {week.label}, {row.day_label}"
    load = _show(row.load_kg) if row.load_kg is not None else "no load logged"
    described: Result = {
        "set_id": row.id,
        "block": block.block_index + 1,
        "tab": block.sheet_name,
        "week": week.week_number,
        "week_label": week.label,
        "week_of": week.start_date.isoformat() if week.start_date else None,
        "day": row.day_label,
        "movement": row.movement_raw,
        "lift": row.lift,
        "variation": row.variation,
        "sets": row.sets,
        "reps": row.reps,
        "rpe": _rpe_text(row),
        "sheet_cell": row.sheet_cell,
        "issues": [issue.message for issue in row.issues],
        "description": (
            f"{row.movement_raw} {row.sets or '?'}x{row.reps_raw} at {load}, RPE {_rpe_text(row)} "
            f"({where}; tab {block.sheet_name!r}, cell {row.sheet_cell})"
        ),
    }
    if row.load_kg is not None:
        described |= _loads("load", row.load_kg)
    return described


class ProgramTools:
    """The tools, bound to one lifter's stored program."""

    def __init__(self, session: Session, lifter: str, warehouse: Warehouse | None = None) -> None:
        self.session = session
        self.lifter = lifter
        self.warehouse = warehouse

    def _upload(self) -> Upload | None:
        return latest_upload(self.session, self.lifter)

    def _rows(self, lift: str, variation: str | None) -> list[ProgramRow]:
        """The lifter's logged sets of one lift variation that have a load, newest first."""
        upload = self._upload()
        if upload is None:
            return []
        query = (
            select(ProgramRow)
            .join(Week)
            .join(Block)
            .where(
                Block.upload_id == upload.id,
                ProgramRow.lift == lift,
                ProgramRow.variation == (variation or COMPETITION),
                ProgramRow.load_kg.is_not(None),
            )
            .order_by(Week.sequence.desc(), ProgramRow.day_order.desc(), ProgramRow.row_order)
        )
        return list(self.session.scalars(query))

    def _variations(self, lift: str) -> list[str]:
        upload = self._upload()
        if upload is None:
            return []
        query = (
            select(ProgramRow.variation)
            .join(Week)
            .join(Block)
            .where(
                Block.upload_id == upload.id,
                ProgramRow.lift == lift,
                ProgramRow.load_kg.is_not(None),
            )
            .distinct()
        )
        return sorted(self.session.scalars(query))

    def _check_lift(self, lift: str, variation: str | None) -> Result | None:
        """A no-data result, or None when this lift variation has logged sets."""
        if lift not in MAIN_LIFTS:
            message = f"lift must be one of {', '.join(MAIN_LIFTS)}"
            return {"status": "invalid_input", "message": message}
        if self._upload() is None:
            return {"status": "no_program", "message": "This lifter has not uploaded a program."}
        if not self._rows(lift, variation):
            return {
                "status": "no_match",
                "message": f"No logged {variation or COMPETITION} {lift} sets with a load.",
                "variations_with_data": self._variations(lift),
            }
        return None

    def find_sets(
        self,
        lift: str,
        variation: str | None = None,
        week_number: int | None = None,
        block: int | None = None,
        reps: int | None = None,
        stated_load: float | None = None,
        stated_rpe: float | None = None,
        unit: str = "lb",
    ) -> Result:
        """Find the logged set a lifter is describing. Looks at the most recent matching week."""
        problem = self._check_lift(lift, variation)
        if problem:
            return problem
        rows = self._rows(lift, variation)
        if block is not None:
            rows = [row for row in rows if row.week.block.block_index + 1 == block]
        if week_number is not None:
            rows = [row for row in rows if row.week.week_number == week_number]
        in_week = rows
        if reps is not None:
            rows = [row for row in rows if row.reps == reps]
        if not rows:
            return {
                "status": "no_match",
                "message": "No logged set matches that lift, week and rep count.",
                "sets_in_that_week": [describe_set(row) for row in in_week[:MAX_LISTED_SETS]],
            }

        latest_week = rows[0].week_id
        candidates = [row for row in rows if row.week_id == latest_week]
        older_matches = len({row.week_id for row in rows}) - 1

        if stated_load is not None:
            stated_kg = _to_kg(stated_load, unit)
            matching = [
                row
                for row in candidates
                if abs(row.load_kg - stated_kg) <= LOAD_TOLERANCE * row.load_kg
            ]
            if not matching:
                return {
                    "status": "conflict",
                    "message": (
                        f"The lifter said {stated_load:g} {unit}, but the log for that week "
                        "shows a different load."
                    ),
                    "logged_sets": [describe_set(row) for row in candidates[:MAX_LISTED_SETS]],
                }
            candidates = matching

        if stated_rpe is not None:
            disagreeing = [
                row
                for row in candidates
                if row.rpe_below_5 or (row.rpe is not None and abs(row.rpe - stated_rpe) > 0.01)
            ]
            if disagreeing and len(disagreeing) == len(candidates):
                return {
                    "status": "conflict",
                    "message": (
                        f"The lifter said RPE {stated_rpe:g}, but the log shows a different RPE."
                    ),
                    "logged_sets": [describe_set(row) for row in candidates[:MAX_LISTED_SETS]],
                }
            candidates = [row for row in candidates if row not in disagreeing]

        distinct = {(row.load_kg, row.reps, row.rpe, row.rpe_below_5) for row in candidates}
        if len(distinct) > 1:
            return {
                "status": "ambiguous",
                "message": "Several different logged sets match. Ask which one the lifter means.",
                "matching_sets": [describe_set(row) for row in candidates[:MAX_LISTED_SETS]],
            }
        return {
            "status": "ok",
            "set": describe_set(candidates[0]),
            "older_weeks_also_matching": older_matches,
        }

    def latest_top_set(self, lift: str, variation: str | None = None) -> Result:
        """The most recent top set usable as a basis: heaviest set of the latest day, RPE 6+."""
        problem = self._check_lift(lift, variation)
        if problem:
            return problem
        rows = [row for row in self._rows(lift, variation) if row.reps]
        qualifying = [row for row in rows if row.rpe is not None and row.rpe >= CHART_MIN_RPE]
        if not qualifying:
            return {
                "status": "no_match",
                "message": (
                    f"No logged {variation or COMPETITION} {lift} set has an RPE of "
                    f"{CHART_MIN_RPE:g} or higher, so there is no reliable basis set."
                ),
                "sets_logged_below_rpe_5": sum(row.rpe_below_5 for row in rows),
                "sets_logged_at_rpe_5_to_6": sum(
                    row.rpe is not None and row.rpe < CHART_MIN_RPE for row in rows
                ),
                "sets_without_rpe": sum(row.rpe is None and not row.rpe_below_5 for row in rows),
            }
        # rows are newest first, so the first qualifying row fixes the week and day
        newest = qualifying[0]
        same_day = [
            row
            for row in qualifying
            if row.week_id == newest.week_id and row.day_order == newest.day_order
        ]
        top = max(same_day, key=lambda row: row.load_kg)
        return {
            "status": "ok",
            "set": describe_set(top),
            "rule": (
                f"most recent week with an RPE {CHART_MIN_RPE:g}+ set; heaviest such set of "
                "its latest day"
            ),
        }

    def _basis(
        self,
        set_id: int | None,
        lift: str | None,
        variation: str | None,
        stated_load: float | None,
        unit: str,
        stated_reps: int | None,
        stated_rpe: float | None,
    ) -> tuple[float, int, float, Result | None, str] | Result:
        """Resolve a calculation's inputs to (load_kg, reps, rpe, set, rpe_source) or an error.

        The basis is a logged set (set_id), else a set the lifter stated in full, else
        the lift's latest top set.
        """
        rpe = stated_rpe
        chosen_by = None
        if set_id is None and stated_load is not None:
            if stated_reps is None or stated_rpe is None:
                message = "A stated set needs stated_load, stated_reps and stated_rpe."
                return {"status": "invalid_input", "message": message}
            return _to_kg(stated_load, unit), stated_reps, stated_rpe, None, "stated"
        if set_id is None:
            if lift is None:
                message = (
                    "Say what to base this on: set_id of a logged set, or lift to use the "
                    "latest top set, or stated_load with stated_reps and stated_rpe."
                )
                return {"status": "invalid_input", "message": message}
            top = self.latest_top_set(lift, variation)
            if top["status"] != "ok":
                return top
            set_id, chosen_by = top["set"]["set_id"], top["rule"]
        row = self.session.get(ProgramRow, set_id)
        upload = self._upload()
        if row is None or upload is None or row.week.block.upload_id != upload.id:
            return {"status": "no_match", "message": f"No logged set has set_id {set_id}."}
        described = describe_set(row)
        if chosen_by:
            described["chosen_by"] = chosen_by
        if row.load_kg is None or not row.reps:
            message = "That set has no usable load or rep count."
            return {"status": "cannot_calculate", "message": message, "set": described}
        if row.rpe is not None:
            return row.load_kg, row.reps, row.rpe, described, "logged"
        if rpe is None:
            return {
                "status": "cannot_calculate",
                "message": (
                    f"That set's RPE is {_rpe_text(row)}, so an e1RM cannot be estimated from "
                    "it. Ask the lifter for the RPE or use another set."
                ),
                "set": described,
            }
        if row.rpe_below_5:
            return {
                "status": "conflict",
                "message": f"The lifter said RPE {rpe:g}, but that set is logged as RPE <5.",
                "set": described,
            }
        return row.load_kg, row.reps, rpe, described, "stated by the lifter (not in the log)"

    def _estimate(self, basis: tuple[float, int, float, Result | None, str]) -> Result:
        """An e1RM result. `_e1rm_kg_exact` keeps full precision for a following calculation."""
        load_kg, reps, rpe, described, rpe_source = basis
        e1rm_kg = e1rm_from_rpe(load_kg, reps, rpe)
        result: Result = {
            "status": "ok",
            **_loads("e1rm", e1rm_kg),
            "e1rm_text": _show(e1rm_kg),
            "based_on": {
                **_loads("load", load_kg),
                "reps": reps,
                "rpe": rpe,
                "rpe_source": rpe_source,
                "reps_in_reserve": MAX_RPE - rpe,
            },
            "method": FORMULA_NOTE,
            "below_chart_range": below_chart_range(rpe),
            "_e1rm_kg_exact": e1rm_kg,
        }
        if described:
            result["set"] = described
        return result

    @staticmethod
    def _finish(result: Result) -> Result:
        result.pop("_e1rm_kg_exact", None)
        if result["below_chart_range"]:
            result["note"] = BELOW_CHART_NOTE
        return result

    def estimate_e1rm(
        self,
        set_id: int | None = None,
        lift: str | None = None,
        variation: str | None = None,
        stated_load: float | None = None,
        unit: str = "lb",
        stated_reps: int | None = None,
        stated_rpe: float | None = None,
    ) -> Result:
        """Estimated one-rep max from a logged set, a lift's latest top set, or a stated set."""
        basis = self._basis(set_id, lift, variation, stated_load, unit, stated_reps, stated_rpe)
        if isinstance(basis, dict):
            return basis
        return self._finish(self._estimate(basis))

    def target_load(
        self,
        target_reps: int,
        target_rpe: float,
        set_id: int | None = None,
        lift: str | None = None,
        variation: str | None = None,
        stated_load: float | None = None,
        unit: str = "lb",
        stated_reps: int | None = None,
        stated_rpe: float | None = None,
    ) -> Result:
        """Load for a prescription (target_reps at target_rpe), from one basis set."""
        basis = self._basis(set_id, lift, variation, stated_load, unit, stated_reps, stated_rpe)
        if isinstance(basis, dict):
            return basis
        estimate = self._estimate(basis)
        target_kg = weight_for_rpe(estimate["_e1rm_kg_exact"], target_reps, target_rpe)
        result: Result = {
            "status": "ok",
            **_loads("target_load", target_kg),
            "target_load_text": _show(target_kg),
            "target": {
                "reps": target_reps,
                "rpe": target_rpe,
                "reps_in_reserve": MAX_RPE - target_rpe,
            },
            **{key: value for key, value in estimate.items() if key != "status"},
        }
        result["below_chart_range"] = estimate["below_chart_range"] or below_chart_range(target_rpe)
        return self._finish(result)

    def _report_source(self) -> tuple[Warehouse, int] | Result:
        """The summary tables and this lifter's id in them, or why they cannot be read."""
        if self.warehouse is None or not self.warehouse.available:
            return {
                "status": "no_warehouse",
                "kind": "report",
                "message": (
                    "The training and nutrition summary tables have not been built yet. "
                    "Run the pipeline (uv run python -m kiloplan.pipeline) and ask again."
                ),
            }
        lifter = self.session.scalar(select(Lifter).where(Lifter.name == self.lifter))
        if lifter is None:
            message = "Nothing has been logged yet."
            return {"status": "no_match", "kind": "report", "message": message}
        return self.warehouse, lifter.id

    def _as_of(self) -> str:
        built = self.warehouse.built_at if self.warehouse else None
        return built.strftime("%Y-%m-%d %H:%M UTC") if built else "unknown"

    def weekly_volume(self, lift: str, weeks: int = 4) -> Result:
        """Training volume (sets, reps and tonnage) for a lift over its most recent weeks."""
        if lift not in MAIN_LIFTS:
            message = f"lift must be one of {', '.join(MAIN_LIFTS)}"
            return {"status": "invalid_input", "message": message}
        source = self._report_source()
        if isinstance(source, dict):
            return source
        warehouse, lifter_id = source
        rows = warehouse.weekly_volume(lifter_id, lift, max(1, min(weeks, MAX_REPORT_WEEKS)))
        if not rows:
            message = f"No {lift} training is in the summary tables, last built {self._as_of()}."
            return {"status": "no_match", "kind": "report", "message": message}
        listed = [
            {
                "block": row["block_index"] + 1,
                "week": row["week_number"],
                "week_of": row["week_start"].isoformat() if row["week_start"] else None,
                "total_sets": int(row["total_sets"]),
                "total_reps": int(row["total_reps"]),
                **_loads("volume", row["volume_kg"]),
                **_loads("top_load", row["top_load_kg"]),
            }
            for row in rows
        ]
        lines = [
            f"block {week['block']} week {week['week']}: {week['total_sets']} sets, "
            f"{week['total_reps']} total reps, "
            f"{week['volume_lb']:.1f} lb ({week['volume_kg']:.1f} kg) of volume"
            for week in listed
        ]
        # added up here so the model never has to
        total = {
            "weeks": len(listed),
            "total_sets": sum(week["total_sets"] for week in listed),
            "total_reps": sum(week["total_reps"] for week in listed),
            **_loads("volume", sum(row["volume_kg"] for row in rows)),
        }
        text = f"{lift.capitalize()} volume, newest week first: " + "; ".join(lines) + "."
        if len(listed) > 1:
            text += (
                f" Total over these {total['weeks']} weeks: {total['volume_lb']:.1f} lb "
                f"({total['volume_kg']:.1f} kg)."
            )
        return {
            "status": "ok",
            "lift": lift,
            "weeks": listed,
            "total_over_these_weeks": total,
            "text": text,
            "as_of": self._as_of(),
        }

    def daily_macros(self, days: int = 1) -> Result:
        """Calories and macros logged over the last `days` days, ending today, with the goal."""
        source = self._report_source()
        if isinstance(source, dict):
            return source
        warehouse, lifter_id = source
        days = max(1, min(days, MAX_REPORT_DAYS))
        today = date.today()
        rows = warehouse.daily_macros(lifter_id, today - timedelta(days=days - 1), today)
        if not rows:
            return {
                "status": "no_match",
                "kind": "report",
                "message": (
                    f"No food is in the summary tables for the last {days} day(s). They were "
                    f"last built {self._as_of()}; food logged since then is not in them yet."
                ),
            }
        keys = ("kcal", "protein_g", "carbs_g", "fat_g")
        listed = [
            {"date": row["diary_date"].isoformat(), **{key: round(row[key], 1) for key in keys}}
            for row in rows
        ]
        average = {key: round(sum(row[key] for row in rows) / len(rows), 1) for key in keys}
        goal = self.session.get(NutritionGoal, lifter_id)
        result: Result = {
            "status": "ok",
            "days_requested": days,
            "days_with_food_logged": len(listed),
            "days": listed,
            "average_per_logged_day": average,
            "as_of": self._as_of(),
        }
        lines = [
            f"{day['date']}: {day['kcal']:.0f} kcal, {day['protein_g']:.0f} g protein, "
            f"{day['carbs_g']:.0f} g carbs, {day['fat_g']:.0f} g fat"
            for day in listed
        ]
        result["text"] = "Food logged, newest day first: " + "; ".join(lines) + "."
        if days > 1 and len(listed) < days:
            result["note"] = (
                f"Only {len(listed)} of the last {days} days have food logged, so the average "
                "covers those days only."
            )
        if goal is not None:
            result["daily_goal"] = {key: round(getattr(goal, key), 1) for key in keys}
        return result

    def call(self, name: str, arguments: dict[str, Any]) -> Result:
        """Run a tool by name. Bad names and arguments come back as results, not exceptions."""
        tools: dict[str, Callable[..., Result]] = {
            "find_sets": self.find_sets,
            "latest_top_set": self.latest_top_set,
            "estimate_e1rm": self.estimate_e1rm,
            "target_load": self.target_load,
            "weekly_volume": self.weekly_volume,
            "daily_macros": self.daily_macros,
        }
        if name not in tools:
            message = f"There is no tool {name!r}. Tools: {', '.join(tools)}."
            return {"status": "invalid_input", "message": message}
        # models send "" or null for parameters they mean to leave out
        given = {key: value for key, value in arguments.items() if value not in (None, "")}
        parameters = inspect.signature(tools[name]).parameters
        unknown = sorted(set(given) - set(parameters))
        missing = [
            key
            for key, parameter in parameters.items()
            if parameter.default is inspect.Parameter.empty and key not in given
        ]
        if unknown or missing:
            problems = [f"it has no parameter {key}" for key in unknown]
            problems += [f"{key} is required" for key in missing]
            message = f"{name} was called wrongly: {'; '.join(problems)}. Its parameters are: "
            return {"status": "invalid_input", "message": message + ", ".join(parameters) + "."}
        try:
            return tools[name](**given)
        except (TypeError, ValueError) as error:
            return {"status": "invalid_input", "message": str(error)}


_LIFT = {"type": "string", "enum": list(MAIN_LIFTS)}
_VARIATION = {
    "type": "string",
    "description": (
        "Lift variation, e.g. 'paused', 'close grip', '4-2-0 tempo'. Leave out for the "
        "competition lift."
    ),
}
_UNIT = {"type": "string", "enum": ["lb", "kg"], "description": "Unit of the load given."}
_BASIS = {
    "set_id": {"type": "integer", "description": "set_id of a logged set, from find_sets."},
    "lift": {**_LIFT, "description": "Base it on this lift's latest top set (no set_id needed)."},
    "variation": _VARIATION,
    "stated_load": {
        "type": "number",
        "description": "Load of a past set the lifter stated. Only when there is no logged set.",
    },
    "unit": _UNIT,
    "stated_reps": {"type": "integer", "description": "Reps of that stated past set."},
    "stated_rpe": {
        "type": "number",
        "description": "RPE of that stated past set, or of a logged set whose RPE is not logged.",
    },
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "find_sets",
        "description": (
            "Look up the logged set a lifter describes, in the most recent matching week. Pass "
            "what the lifter said (stated_load, stated_rpe) so it can be checked against the log."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lift": _LIFT,
                "variation": _VARIATION,
                "week_number": {"type": "integer", "description": "Week within its block."},
                "block": {"type": "integer", "description": "Block number, 1 is the oldest."},
                "reps": {"type": "integer", "description": "Reps of the past set."},
                "stated_load": {"type": "number", "description": "Load the lifter said."},
                "stated_rpe": {"type": "number", "description": "RPE the lifter said."},
                "unit": _UNIT,
            },
            "required": ["lift"],
        },
    },
    {
        "name": "latest_top_set",
        "description": "The lifter's most recent top set of a lift with RPE 6 or higher.",
        "parameters": {
            "type": "object",
            "properties": {"lift": _LIFT, "variation": _VARIATION},
            "required": ["lift"],
        },
    },
    {
        "name": "estimate_e1rm",
        "description": (
            "Estimated one-rep max. Base it on a logged set (set_id), or on a lift's latest "
            "top set (lift)."
        ),
        "parameters": {"type": "object", "properties": _BASIS, "required": []},
    },
    {
        "name": "target_load",
        "description": (
            "The weight to use for the new prescription: target_reps at target_rpe. Base it on "
            "a logged set (set_id from find_sets) when the lifter names a past set, or on a "
            "lift's latest top set (lift) when they do not. Returns the e1RM it used as well."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_reps": {"type": "integer", "description": "Reps the lifter will do."},
                "target_rpe": {"type": "number", "description": "RPE the lifter should hit."},
                **_BASIS,
            },
            "required": ["target_reps", "target_rpe"],
        },
    },
    {
        "name": "weekly_volume",
        "description": (
            "Training volume for a lift over its most recent weeks: sets, reps and tonnage "
            "per week. Use for questions about volume or how much work was done."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "lift": _LIFT,
                "weeks": {"type": "integer", "description": "How many recent weeks. Default 4."},
            },
            "required": ["lift"],
        },
    },
    {
        "name": "daily_macros",
        "description": (
            "Calories, protein, carbs and fat the lifter logged over the last days, ending "
            "today, with their daily goal and the average. Use for any food or macro question."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "How many days back. 1 means today."}
            },
            "required": [],
        },
    },
]
