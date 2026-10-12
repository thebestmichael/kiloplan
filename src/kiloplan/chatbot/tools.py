"""Tools the assistant calls to look up a lifter's logged sets and to calculate loads.

Every number in an answer must come from one of these results, so each tool decides
its own `status` in code and returns loads in both kg and lb, already rounded for
display.
"""

from collections.abc import Callable
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
from kiloplan.storage.models import Block, Lifter, PerformedSet, Upload, Week
from kiloplan.storage.program_store import latest_upload

KG_PER_LB = 0.45359237
MAIN_LIFTS = ("squat", "bench", "deadlift")
# a stated load matches a logged one within this share of the logged load
LOAD_TOLERANCE = 0.01
MAX_LISTED_SETS = 8

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


def _rpe_text(performed: PerformedSet) -> str:
    if performed.rpe_below_5:
        return "<5"
    return "not logged" if performed.rpe is None else f"{performed.rpe:g}"


def describe_set(performed: PerformedSet) -> Result:
    """A logged set as the assistant sees it."""
    row = performed.program_row
    reps = row.reps_raw if row else f"{performed.reps or '?'}"
    summary = (
        f"{performed.movement_raw} {performed.sets or '?'}x{reps} at "
        f"{_show(performed.load_kg)}, RPE {_rpe_text(performed)}"
    )
    described: Result = {
        "set_id": performed.id,
        "movement": performed.movement_raw,
        "lift": performed.lift,
        "variation": performed.variation,
        "sets": performed.sets,
        "reps": performed.reps,
        "rpe": _rpe_text(performed),
        **_loads("load", performed.load_kg),
    }
    if row is None:
        day = performed.performed_on
        when = f"logged on {day.isoformat()}" if day else "logged in the app"
        return described | {
            "date": day.isoformat() if day else None,
            "description": f"{summary} ({when})",
        }
    week, block = row.week, row.week.block
    where = f"block {block.block_index + 1}, {week.label}, {row.day_label}"
    return described | {
        "block": block.block_index + 1,
        "tab": block.sheet_name,
        "week": week.week_number,
        "week_label": week.label,
        "week_of": week.start_date.isoformat() if week.start_date else None,
        "day": row.day_label,
        "sheet_cell": row.sheet_cell,
        "issues": [issue.message for issue in row.issues],
        "description": f"{summary} ({where}; tab {block.sheet_name!r}, cell {row.sheet_cell})",
    }


def _week_number(performed: PerformedSet) -> int | None:
    row = performed.program_row
    return row.week.week_number if row else None


def _block_number(performed: PerformedSet) -> int | None:
    row = performed.program_row
    return row.week.block.block_index + 1 if row else None


def _week_key(performed: PerformedSet) -> tuple[Any, ...]:
    """Identifies the training week a set belongs to: its program week, else its calendar week."""
    row, day = performed.program_row, performed.performed_on
    if row:
        return "program", row.week_id
    return ("app", *day.isocalendar()[:2]) if day else ("app", performed.id)


def _day_key(performed: PerformedSet) -> tuple[Any, ...]:
    """Identifies the training day a set belongs to."""
    row, day = performed.program_row, performed.performed_on
    if row:
        return "program", row.week_id, row.day_order
    return ("app", day) if day else ("app", performed.id)


class ProgramTools:
    """The tools, bound to one lifter's stored program."""

    def __init__(self, session: Session, lifter: str) -> None:
        self.session = session
        self.lifter = lifter

    def _upload(self) -> Upload | None:
        return latest_upload(self.session, self.lifter)

    def _lifter_id(self) -> int | None:
        return self.session.scalar(select(Lifter.id).where(Lifter.name == self.lifter))

    def _recency(self) -> Callable[[PerformedSet], tuple[int, ...]]:
        """A sort key that puts a lifter's sets oldest first.

        Sets from the program follow its week, day and row order. A set logged in the
        app comes after the latest program week that had started by its date.
        """
        dated_weeks = self.session.execute(
            select(Week.start_date, Week.sequence)
            .join(Block)
            .join(Upload)
            .where(Upload.lifter_id == self._lifter_id(), Week.start_date.is_not(None))
        ).all()

        def key(performed: PerformedSet) -> tuple[int, ...]:
            row, day = performed.program_row, performed.performed_on
            if row:
                # rows are read top to bottom, so within a day the first row sorts newest
                return row.week.sequence, 0, row.day_order, -row.row_order
            sequence = max((seq for start, seq in dated_weeks if day and start <= day), default=-1)
            return sequence, 1, day.toordinal() if day else 0, performed.id

        return key

    def _rows(self, lift: str, variation: str | None) -> list[PerformedSet]:
        """The lifter's performed sets of one lift variation, newest first."""
        query = select(PerformedSet).where(
            PerformedSet.lifter_id == self._lifter_id(),
            PerformedSet.lift == lift,
            PerformedSet.variation == (variation or COMPETITION),
        )
        return sorted(self.session.scalars(query), key=self._recency(), reverse=True)

    def _variations(self, lift: str) -> list[str]:
        query = (
            select(PerformedSet.variation)
            .where(PerformedSet.lifter_id == self._lifter_id(), PerformedSet.lift == lift)
            .distinct()
        )
        return sorted(self.session.scalars(query))

    def _has_sets(self) -> bool:
        query = select(PerformedSet.id).where(PerformedSet.lifter_id == self._lifter_id()).limit(1)
        return self.session.scalar(query) is not None

    def _check_lift(self, lift: str, variation: str | None) -> Result | None:
        """A no-data result, or None when this lift variation has logged sets."""
        if lift not in MAIN_LIFTS:
            message = f"lift must be one of {', '.join(MAIN_LIFTS)}"
            return {"status": "invalid_input", "message": message}
        if self._upload() is None and not self._has_sets():
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
            rows = [row for row in rows if _block_number(row) == block]
        if week_number is not None:
            rows = [row for row in rows if _week_number(row) == week_number]
        in_week = rows
        if reps is not None:
            rows = [row for row in rows if row.reps == reps]
        if not rows:
            return {
                "status": "no_match",
                "message": "No logged set matches that lift, week and rep count.",
                "sets_in_that_week": [describe_set(row) for row in in_week[:MAX_LISTED_SETS]],
            }

        latest_week = _week_key(rows[0])
        candidates = [row for row in rows if _week_key(row) == latest_week]
        older_matches = len({_week_key(row) for row in rows}) - 1

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
        same_day = [row for row in qualifying if _day_key(row) == _day_key(qualifying[0])]
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
        self, set_id: int | None, load: float | None, unit: str, reps: int | None, rpe: float | None
    ) -> tuple[float, int, float, Result | None, str] | Result:
        """Resolve a calculation's inputs to (load_kg, reps, rpe, set, rpe_source) or an error."""
        if set_id is None:
            if load is None or reps is None or rpe is None:
                message = "Give either set_id, or load, reps and rpe."
                return {"status": "invalid_input", "message": message}
            return _to_kg(load, unit), reps, rpe, None, "stated"
        row = self.session.get(PerformedSet, set_id)
        if row is None or row.lifter_id != self._lifter_id():
            return {"status": "no_match", "message": f"No logged set has set_id {set_id}."}
        described = describe_set(row)
        if not row.reps:
            message = "That set has no usable rep count."
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
        load: float | None = None,
        unit: str = "lb",
        reps: int | None = None,
        rpe: float | None = None,
    ) -> Result:
        """Estimated one-rep max from a logged set (by set_id) or from load, reps and RPE."""
        basis = self._basis(set_id, load, unit, reps, rpe)
        if isinstance(basis, dict):
            return basis
        return self._finish(self._estimate(basis))

    def target_load(
        self,
        target_reps: int,
        target_rpe: float,
        set_id: int | None = None,
        load: float | None = None,
        unit: str = "lb",
        reps: int | None = None,
        rpe: float | None = None,
    ) -> Result:
        """Load for a prescription (reps at an RPE), from a logged set or a stated set."""
        basis = self._basis(set_id, load, unit, reps, rpe)
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

    def call(self, name: str, arguments: dict[str, Any]) -> Result:
        """Run a tool by name. Bad names and arguments come back as results, not exceptions."""
        tools: dict[str, Callable[..., Result]] = {
            "find_sets": self.find_sets,
            "latest_top_set": self.latest_top_set,
            "estimate_e1rm": self.estimate_e1rm,
            "target_load": self.target_load,
        }
        if name not in tools:
            return {"status": "invalid_input", "message": f"Unknown tool {name!r}."}
        try:
            return tools[name](
                **{key: value for key, value in arguments.items() if value is not None}
            )
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
    "set_id": {"type": "integer", "description": "set_id of a logged set from a lookup tool."},
    "load": {"type": "number", "description": "Load of a set the lifter stated; not with set_id."},
    "unit": _UNIT,
    "reps": {"type": "integer", "description": "Reps of the stated set; not with set_id."},
    "rpe": {
        "type": "number",
        "description": "RPE of the stated set, or of a logged set whose RPE was not logged.",
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
                "reps": {"type": "integer"},
                "stated_load": {"type": "number"},
                "stated_rpe": {"type": "number"},
                "unit": _UNIT,
            },
            "required": ["lift"],
        },
    },
    {
        "name": "latest_top_set",
        "description": (
            "The lifter's most recent top set of a lift with RPE 6 or higher. Use when the "
            "lifter does not name a past set."
        ),
        "parameters": {
            "type": "object",
            "properties": {"lift": _LIFT, "variation": _VARIATION},
            "required": ["lift"],
        },
    },
    {
        "name": "estimate_e1rm",
        "description": "Estimated one-rep max from a logged set (set_id) or a stated set.",
        "parameters": {"type": "object", "properties": _BASIS, "required": []},
    },
    {
        "name": "target_load",
        "description": (
            "The load to use for a prescription of target_reps at target_rpe, based on a logged "
            "set (set_id) or a stated set. Returns the e1RM it used as well."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_reps": {"type": "integer"},
                "target_rpe": {"type": "number"},
                **_BASIS,
            },
            "required": ["target_reps", "target_rpe"],
        },
    },
]
