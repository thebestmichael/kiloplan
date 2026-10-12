"""Builders for small synthetic coach workbooks used across the tests."""

from io import BytesIO

from openpyxl import Workbook

OLD_HEADER = ["Sets", "Reps", "Intensity ", "Target Load", "Actual load", "Last Set RPE"]
NEW_HEADER = ["Movement ", "SET", "REPS", "INTENSITY", "TARGET LOAD", "TRUE LOAD", "RPE(LAST SET)"]
WEEK_WIDTH = 8


def put(sheet, row, column, values):
    for offset, value in enumerate(values):
        sheet.cell(row=row, column=column + offset, value=value)


def add_old_week(sheet, column, label, dates, days):
    """Older tab layout: "Day N" header, movement in the day column, 8 columns per week."""
    put(sheet, 1, column, [label])
    put(sheet, 2, column, ["Date", dates])
    row = 4
    for day_label, lines in days:
        put(sheet, row, column, [day_label, *OLD_HEADER])
        for line in lines:
            row += 1
            put(sheet, row, column, line)
        row += 3


def line(movement, sets, reps, load, rpe=None, intensity=None, target=None):
    return [movement, sets, reps, intensity, target, load, rpe]


def program_workbook(sheets):
    """`sheets` maps a tab name to its weeks: (label, dates, {day: [lines]}), left to right."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, weeks in sheets.items():
        sheet = workbook.create_sheet(name)
        for index, (label, dates, days) in enumerate(weeks):
            add_old_week(sheet, 2 + WEEK_WIDTH * index, label, dates, list(days.items()))
    return workbook


def as_bytes(workbook):
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def save(workbook, tmp_path):
    path = tmp_path / "program.xlsx"
    workbook.save(path)
    return path
