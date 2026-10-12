from datetime import date

from sqlalchemy import func, select

from kiloplan.ingestion.coach_sheet import parse_workbook
from kiloplan.storage.models import (
    APP,
    DAY,
    Block,
    Lifter,
    Note,
    PerformedSet,
    ProgramIssue,
    ProgramRow,
    Upload,
    Week,
)
from kiloplan.storage.program_store import latest_upload, store_program
from workbooks import as_bytes, line, program_workbook


def squat_day(load, rpe=7):
    return {"Day 1": [line("Squat", 1, 3, load, rpe)]}


def store(session, sheets, lifter="ana"):
    result = parse_workbook(as_bytes(program_workbook(sheets)))
    upload = store_program(session, lifter, "program.xlsx", result)
    session.commit()
    return upload


def weeks_in_order(session):
    return session.scalars(select(Week).order_by(Week.sequence)).all()


def test_blocks_split_when_the_week_number_drops(session):
    store(
        session,
        {
            "Spring": [
                ("Week 1", "3/2-8/26", squat_day(300)),
                ("Week 2", "3/9-15/26", squat_day(310)),
                ("Week 3", "3/16-22/26", squat_day(320)),
                ("Week 1", "3/23-29/26", squat_day(305)),
                ("Week 2", "3/30-4/5/26", squat_day(315)),
            ]
        },
    )
    weeks = weeks_in_order(session)
    assert [(week.block.block_index, week.week_number, week.sequence) for week in weeks] == [
        (0, 1, 0),
        (0, 2, 1),
        (0, 3, 2),
        (1, 1, 3),
        (1, 2, 4),
    ]
    assert weeks[3].start_date == date(2026, 3, 23)
    assert {block.sheet_name for block in session.scalars(select(Block))} == {"Spring"}


def test_a_repeated_week_number_stays_in_the_block_and_is_reported(session):
    upload = store(
        session,
        {
            "Spring": [
                ("Week 1", "3/2-8/26", squat_day(300)),
                ("Week 2", "3/9-15/26", squat_day(310)),
                ("Week 2", "3/16-22/26", squat_day(320)),
            ]
        },
    )
    assert [week.block.block_index for week in weeks_in_order(session)] == [0, 0, 0]
    assert ["appears twice" in issue.message for issue in upload.issues] == [True]


def test_dated_tabs_are_ordered_by_date_not_position(session):
    store(
        session,
        {
            "Newer": [("Week 1", "6/1-7/26", squat_day(330))],
            "Older": [("Week 1", "3/2-8/26", squat_day(300))],
        },
    )
    weeks = weeks_in_order(session)
    assert [week.block.sheet_name for week in weeks] == ["Older", "Newer"]
    assert [week.block.block_index for week in weeks] == [0, 1]


def test_an_undated_tab_is_placed_by_position_in_a_newest_first_workbook(session):
    store(
        session,
        {
            "Current": [("Week 1", None, squat_day(340))],
            "Summer": [("Week 1", "6/1-7/26", squat_day(330))],
            "Spring": [("Week 1", "3/2-8/26", squat_day(300))],
        },
    )
    assert [week.block.sheet_name for week in weeks_in_order(session)] == [
        "Spring",
        "Summer",
        "Current",
    ]


def test_an_undated_tab_is_placed_by_position_in_an_oldest_first_workbook(session):
    store(
        session,
        {
            "Spring": [("Week 1", "3/2-8/26", squat_day(300))],
            "Summer": [("Week 1", "6/1-7/26", squat_day(330))],
            "Current": [("Week 1", None, squat_day(340))],
        },
    )
    assert [week.block.sheet_name for week in weeks_in_order(session)] == [
        "Spring",
        "Summer",
        "Current",
    ]


def test_rows_notes_and_issues_are_stored(session):
    upload = store(
        session,
        {
            "Spring": [
                (
                    "Week 1",
                    "3/2-8/26",
                    {
                        "Day 1": [
                            line("Paused Squats", 1, 3, 405, 9, intensity="@8"),
                            line(None, 3, 5, 365, 11, intensity=-10, target=364.5),
                            ["Notes ", "Knees felt good"],
                        ],
                        "Day 2": [line("Cable Rows", 4, "AMRAP", "60*")],
                    },
                )
            ]
        },
    )
    top, backoff, rows = session.scalars(select(ProgramRow).order_by(ProgramRow.row_order)).all()
    assert (top.movement_raw, top.lift, top.variation) == ("Paused Squats", "squat", "paused")
    assert (top.day_label, top.day_order, top.row_order) == ("Day 1", 0, 0)
    assert (top.sets, top.reps, top.rpe, top.intensity_raw) == (1, 3, 9.0, "@8")
    assert top.load_kg == 405 * 0.45359237
    assert (backoff.lift, backoff.target_load_raw, backoff.rpe) == ("squat", "364.5", None)
    assert (rows.lift, rows.day_order, rows.reps, rows.reps_raw) == ("other", 1, None, "AMRAP")

    note = session.scalars(select(Note)).one()
    assert (note.day_label, note.text, note.week.label) == ("Day 1", "Knees felt good", "Week 1")

    # the invalid RPE is attached to the row it was found on
    issue = session.scalars(select(ProgramIssue)).one()
    assert issue.row is backoff
    assert upload.issues == [issue]


def test_storing_again_replaces_the_lifters_program_only(session):
    store(session, {"Spring": [("Week 1", "3/2-8/26", squat_day(300))]}, lifter="ana")
    store(session, {"Spring": [("Week 1", "3/2-8/26", squat_day(280))]}, lifter="ben")
    store(session, {"Summer": [("Week 1", "6/1-7/26", squat_day(330))]}, lifter="ana")

    assert session.scalar(select(func.count()).select_from(Lifter)) == 2
    assert session.scalar(select(func.count()).select_from(Upload)) == 2
    assert session.scalar(select(func.count()).select_from(ProgramRow)) == 2
    assert latest_upload(session, "ana").blocks[0].sheet_name == "Summer"
    assert latest_upload(session, "ben").blocks[0].sheet_name == "Spring"
    assert latest_upload(session, "nobody") is None


def test_each_row_with_a_load_becomes_a_performed_set(session):
    store(
        session,
        {
            "Spring": [
                (
                    "Week 1",
                    "3/2-8/26",
                    {
                        "Day 1": [
                            line("Paused Squats", 1, 3, 405, 9),
                            line("Leg Press", 3, 10, None),
                        ]
                    },
                )
            ]
        },
    )
    performed = session.scalars(select(PerformedSet)).one()
    assert (performed.lifter.name, performed.source) == ("ana", "coach_sheet")
    assert (performed.performed_on, performed.date_precision) == (date(2026, 3, 2), "week")
    assert (performed.lift, performed.variation, performed.sets, performed.reps) == (
        "squat",
        "paused",
        1,
        3,
    )
    assert (performed.load_kg, performed.rpe) == (405 * 0.45359237, 9.0)
    assert performed.program_row.movement_raw == "Paused Squats"


def test_storing_again_replaces_sheet_sets_and_keeps_app_sets(session):
    store(session, {"Spring": [("Week 1", "3/2-8/26", squat_day(300))]})
    ana = session.scalars(select(Lifter)).one()
    session.add(
        PerformedSet(
            lifter=ana,
            source=APP,
            performed_on=date(2026, 3, 10),
            date_precision=DAY,
            movement_raw="Squat",
            lift="squat",
            variation="competition",
            sets=1,
            reps=2,
            load_kg=150.0,
            rpe=8.0,
        )
    )
    session.commit()

    store(session, {"Summer": [("Week 1", "6/1-7/26", squat_day(330))]})

    sets = session.scalars(select(PerformedSet).order_by(PerformedSet.load_kg)).all()
    assert [(performed.source, round(performed.load_kg, 1)) for performed in sets] == [
        ("coach_sheet", 149.7),
        ("app", 150.0),
    ]
    assert sets[0].program_row.week.block.sheet_name == "Summer"
