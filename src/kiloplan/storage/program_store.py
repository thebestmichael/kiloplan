"""Stores a parsed coach spreadsheet as blocks, weeks and rows for one lifter."""

import re
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from kiloplan.ingestion.coach_sheet import ParseResult, SheetWeek
from kiloplan.ingestion.lifts import classify
from kiloplan.storage.models import (
    Block,
    Lifter,
    Note,
    ProgramIssue,
    ProgramRow,
    Upload,
    Week,
)

WEEK_NUMBER = re.compile(r"\d+")


def _week_number(label: str) -> int | None:
    match = WEEK_NUMBER.search(label)
    return int(match.group()) if match else None


def _first_date(weeks: list[SheetWeek]) -> date | None:
    return min((week.start for week in weeks if week.start), default=None)


def _chronological_sheets(weeks_by_sheet: dict[str, list[SheetWeek]]) -> list[str]:
    """Sheet names, oldest first.

    With every tab dated, tabs are sorted by their first week. If any tab has no
    dates, tab position decides: the dated tabs show whether the workbook runs
    newest-first or oldest-first, and the coach's newest-first is assumed when they
    cannot.
    """
    names = list(weeks_by_sheet)
    firsts = {name: _first_date(weeks_by_sheet[name]) for name in names}
    if all(firsts.values()):
        return sorted(names, key=lambda name: firsts[name])
    dated = [firsts[name] for name in names if firsts[name]]
    rising = sum(later > earlier for earlier, later in zip(dated, dated[1:], strict=False))
    falling = sum(later < earlier for earlier, later in zip(dated, dated[1:], strict=False))
    return names if rising > falling else names[::-1]


def get_or_create_lifter(session: Session, name: str) -> Lifter:
    lifter = session.scalar(select(Lifter).where(Lifter.name == name))
    if lifter is None:
        lifter = Lifter(name=name)
        session.add(lifter)
        session.flush()
    return lifter


def store_program(session: Session, lifter_name: str, filename: str, result: ParseResult) -> Upload:
    """Replace the lifter's stored program with this parse result."""
    lifter = get_or_create_lifter(session, lifter_name)
    for previous in list(lifter.uploads):
        session.delete(previous)
    session.flush()

    upload = Upload(filename=filename, skipped_sheets=result.skipped_sheets)
    lifter.uploads.append(upload)

    weeks_by_sheet: dict[str, list[SheetWeek]] = defaultdict(list)
    for sheet_week in result.weeks:
        weeks_by_sheet[sheet_week.sheet].append(sheet_week)

    stored_weeks: dict[tuple[str, int], Week] = {}
    block_index = sequence = 0
    for sheet in _chronological_sheets(weeks_by_sheet):
        block: Block | None = None
        previous_number: int | None = None
        for sheet_week in sorted(weeks_by_sheet[sheet], key=lambda week: week.week_index):
            number = _week_number(sheet_week.label)
            # a week number that drops (Week 4 then Week 1) starts a new block
            dropped = (
                number is not None and previous_number is not None and number < previous_number
            )
            if block is None or dropped:
                block = Block(sheet_name=sheet, block_index=block_index)
                upload.blocks.append(block)
                block_index += 1
            week = Week(
                week_number=number,
                label=sheet_week.label,
                start_date=sheet_week.start,
                end_date=sheet_week.end,
                sequence=sequence,
            )
            block.weeks.append(week)
            sequence += 1
            stored_weeks[sheet, sheet_week.week_index] = week
            if number is not None and number == previous_number:
                message = f"{sheet_week.label!r} appears twice in a row in this block"
                upload.issues.append(ProgramIssue(sheet=sheet, cell="", message=message))
            if number is not None:
                previous_number = number

    rows_by_cell: dict[tuple[str, str], ProgramRow] = {}
    day_orders: dict[tuple[str, int], dict[str, int]] = defaultdict(dict)
    row_counts: dict[tuple[str, int], int] = defaultdict(int)
    for parsed in result.rows:
        key = (parsed.sheet, parsed.week_index)
        days = day_orders[key]
        lift = classify(parsed.movement)
        row = ProgramRow(
            day_label=parsed.day_label,
            day_order=days.setdefault(parsed.day_label, len(days)),
            row_order=row_counts[key],
            movement_raw=parsed.movement,
            lift=lift.lift,
            variation=lift.variation,
            sets=parsed.sets,
            reps=parsed.reps,
            reps_raw=parsed.reps_raw,
            load_kg=parsed.actual_load_kg,
            load_raw=parsed.actual_load_raw,
            assumed_kg=parsed.assumed_kg,
            rpe=parsed.rpe,
            rpe_below_5=parsed.rpe_below_5,
            intensity_raw=parsed.intensity_raw,
            target_load_raw=parsed.target_load_raw,
            sheet_cell=parsed.cell,
        )
        stored_weeks[key].rows.append(row)
        row_counts[key] += 1
        rows_by_cell[parsed.sheet, parsed.cell] = row

    for note in result.notes:
        stored_weeks[note.sheet, note.week_index].notes.append(
            Note(day_label=note.day_label, text=note.text, sheet_cell=note.cell)
        )

    for issue in result.issues:
        upload.issues.append(
            ProgramIssue(
                row=rows_by_cell.get((issue.sheet, issue.cell)),
                sheet=issue.sheet,
                cell=issue.cell,
                message=issue.message,
            )
        )

    session.flush()
    return upload


def latest_upload(session: Session, lifter_name: str) -> Upload | None:
    return session.scalar(
        select(Upload)
        .join(Lifter)
        .where(Lifter.name == lifter_name)
        .order_by(Upload.id.desc())
        .limit(1)
    )
