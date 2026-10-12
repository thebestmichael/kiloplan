"""FastAPI app. Run with: uv run uvicorn kiloplan.api.main:app --reload"""

from datetime import date
from io import BytesIO
from typing import Literal
from zipfile import BadZipFile

from fastapi import FastAPI, HTTPException, UploadFile
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, Field

from kiloplan.analytics.e1rm import (
    MAX_RPE,
    MIN_RPE,
    brzycki,
    brzycki_weight,
    e1rm_from_rpe,
    epley,
    epley_weight,
    hybrid,
    hybrid_weight,
    weight_for_rpe,
)
from kiloplan.ingestion.coach_sheet import Issue, SheetRow, parse_workbook

app = FastAPI(title="KiloPlan")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

FORMULAS = {
    "hybrid": (hybrid, hybrid_weight),
    "epley": (epley, epley_weight),
    "brzycki": (brzycki, brzycki_weight),
}


class TargetLoadRequest(BaseModel):
    pr_weight_kg: float = Field(gt=0)
    pr_reps: int = Field(ge=1)
    pr_rpe: float = Field(ge=MIN_RPE, le=MAX_RPE)
    target_reps: int = Field(ge=1)
    target_rpe: float = Field(ge=MIN_RPE, le=MAX_RPE)
    formula: Literal["hybrid", "epley", "brzycki"] = "hybrid"


class TargetLoadResponse(BaseModel):
    e1rm_kg: float
    target_weight_kg: float


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/target-load")
def target_load(request: TargetLoadRequest) -> TargetLoadResponse:
    formula, inverse = FORMULAS[request.formula]
    try:
        e1rm_kg = e1rm_from_rpe(request.pr_weight_kg, request.pr_reps, request.pr_rpe, formula)
        target_weight_kg = weight_for_rpe(e1rm_kg, request.target_reps, request.target_rpe, inverse)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return TargetLoadResponse(e1rm_kg=e1rm_kg, target_weight_kg=target_weight_kg)


class SheetSummary(BaseModel):
    name: str
    lines: int
    weeks: int
    first_week: date | None
    last_week: date | None


class ProgramParseResponse(BaseModel):
    sheets: list[SheetSummary]
    skipped_sheets: list[str]
    issues: list[Issue]
    rows: list[SheetRow]


def _summarise(rows: list[SheetRow]) -> list[SheetSummary]:
    by_sheet: dict[str, list[SheetRow]] = {}
    for row in rows:
        by_sheet.setdefault(row.sheet, []).append(row)
    summaries = []
    for name, sheet_rows in by_sheet.items():
        starts = [row.week_start for row in sheet_rows if row.week_start]
        summaries.append(
            SheetSummary(
                name=name,
                lines=len(sheet_rows),
                # the movement column's letters differ for every week of a sheet
                weeks=len({row.cell.rstrip("0123456789") for row in sheet_rows}),
                first_week=min(starts, default=None),
                last_week=max(starts, default=None),
            )
        )
    return summaries


@app.post("/api/program/parse")
def parse_program(file: UploadFile) -> ProgramParseResponse:
    """Parse an uploaded coach spreadsheet and return what was read. Nothing is stored."""
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 20 MB.")
    try:
        result = parse_workbook(BytesIO(content))
    except (BadZipFile, InvalidFileException, KeyError, OSError) as error:
        detail = "Could not read this file as an Excel workbook (.xlsx)."
        raise HTTPException(status_code=400, detail=detail) from error
    return ProgramParseResponse(
        sheets=_summarise(result.rows),
        skipped_sheets=result.skipped_sheets,
        issues=result.issues,
        rows=result.rows,
    )
