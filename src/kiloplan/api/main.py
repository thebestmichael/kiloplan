"""FastAPI app. Run with: uv run uvicorn kiloplan.api.main:app --reload"""

from datetime import date, datetime
from functools import cache
from io import BytesIO
from typing import Annotated, Any, Literal
from zipfile import BadZipFile

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from kiloplan.analytics import scoring
from kiloplan.analytics.attempts import select_attempts
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
    rep_max_table,
    rpe_chart,
    weight_for_rpe,
)
from kiloplan.analytics.plates import bar_total, load_bar
from kiloplan.chatbot.assistant import Assistant
from kiloplan.chatbot.llm import ChatModel, ModelUnavailableError, OllamaModel
from kiloplan.chatbot.tools import ProgramTools
from kiloplan.ingestion.coach_sheet import parse_workbook
from kiloplan.storage.db import get_session
from kiloplan.storage.models import Upload
from kiloplan.storage.program_store import latest_upload, store_program

app = FastAPI(title="KiloPlan")

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
DEFAULT_LIFTER = "default"

DbSession = Annotated[Session, Depends(get_session)]

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


class RepMaxRequest(BaseModel):
    weight_kg: float = Field(gt=0)
    reps: int = Field(ge=1, le=20)
    rpe: float = Field(ge=MIN_RPE, le=MAX_RPE)


class RepMax(BaseModel):
    reps: int
    weight_kg: float


class RpeChartRow(BaseModel):
    rpe: float
    weights_kg: list[float]


class RepMaxResponse(BaseModel):
    e1rm_kg: float
    rep_maxes: list[RepMax]
    rpe_chart: list[RpeChartRow]


@app.post("/api/rep-maxes")
def rep_maxes(request: RepMaxRequest) -> RepMaxResponse:
    """Estimated 1 to 10 rep maxes and an RPE chart from one set."""
    e1rm_kg = e1rm_from_rpe(request.weight_kg, request.reps, request.rpe)
    return RepMaxResponse(
        e1rm_kg=e1rm_kg,
        rep_maxes=[
            RepMax(reps=reps, weight_kg=weight) for reps, weight in rep_max_table(e1rm_kg).items()
        ],
        rpe_chart=[
            RpeChartRow(rpe=rpe, weights_kg=list(weights.values()))
            for rpe, weights in rpe_chart(e1rm_kg).items()
        ],
    )


class PlateStock(BaseModel):
    weight: float = Field(gt=0)
    pairs: int = Field(ge=0, le=50)


class PlateRequest(BaseModel):
    """Weights are in the unit of the plates, kg or lb."""

    target: float = Field(gt=0, le=2000)
    bar: float = Field(ge=0)
    collar: float = Field(default=0, ge=0)
    plates: list[PlateStock] = Field(max_length=30)


class PlateResponse(BaseModel):
    per_side: list[float]
    total: float
    shortfall: float


@app.post("/api/plates")
def plates(request: PlateRequest) -> PlateResponse:
    """Plates per side to load a target weight from the plates available."""
    stock = {plate.weight: plate.pairs for plate in request.plates}
    try:
        load = load_bar(request.target, request.bar, stock, request.collar)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return PlateResponse(per_side=list(load.per_side), total=load.total, shortfall=load.shortfall)


class BarTotalRequest(BaseModel):
    per_side: list[float] = Field(max_length=40)
    bar: float = Field(ge=0)
    collar: float = Field(default=0, ge=0)


@app.post("/api/plates/total")
def plates_total(request: BarTotalRequest) -> dict[str, float]:
    """The reverse calculation: total weight of a loaded bar."""
    try:
        return {"total": bar_total(request.per_side, request.bar, request.collar)}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


class PointsRequest(BaseModel):
    sex: Literal["male", "female"]
    bodyweight_kg: float = Field(gt=0, le=400)
    total_kg: float = Field(ge=0, le=2000)
    equipped: bool = False
    bench_only: bool = False


class PointsResponse(BaseModel):
    wilks: float
    wilks_2020: float
    dots: float
    ipf_gl: float


@app.post("/api/points")
def points(request: PointsRequest) -> PointsResponse:
    sex, bodyweight, total = request.sex, request.bodyweight_kg, request.total_kg
    return PointsResponse(
        wilks=scoring.wilks(sex, bodyweight, total),
        wilks_2020=scoring.wilks_2020(sex, bodyweight, total),
        dots=scoring.dots(sex, bodyweight, total),
        ipf_gl=scoring.ipf_gl(sex, bodyweight, total, request.equipped, request.bench_only),
    )


class AttemptsRequest(BaseModel):
    """Goal third attempts in kg. Leave a lift out to skip it."""

    squat_kg: float | None = Field(default=None, gt=0)
    bench_kg: float | None = Field(default=None, gt=0)
    deadlift_kg: float | None = Field(default=None, gt=0)


class AttemptsResponse(BaseModel):
    attempts_kg: dict[str, list[float]]
    total_kg: float


@app.post("/api/attempts")
def attempts(request: AttemptsRequest) -> AttemptsResponse:
    """Opener, second and third attempts for each goal, and the total of the thirds."""
    goals = {"squat": request.squat_kg, "bench": request.bench_kg, "deadlift": request.deadlift_kg}
    chosen = {lift: list(select_attempts(goal)) for lift, goal in goals.items() if goal}
    return AttemptsResponse(
        attempts_kg=chosen, total_kg=sum(lift_attempts[-1] for lift_attempts in chosen.values())
    )


class SheetSummary(BaseModel):
    name: str
    blocks: int
    weeks: int
    lines: int
    first_week: date | None
    last_week: date | None


class ProgramIssueOut(BaseModel):
    sheet: str
    cell: str
    message: str


class ProgramRowOut(BaseModel):
    id: int
    block_index: int
    sheet: str
    cell: str
    week_number: int | None
    week_label: str
    week_start: date | None
    day_label: str
    movement: str
    lift: str
    variation: str
    sets: int | None
    reps_raw: str
    intensity_raw: str
    target_load_raw: str
    actual_load_raw: str
    actual_load_kg: float | None
    rpe: float | None
    rpe_below_5: bool
    assumed_kg: bool


class ProgramResponse(BaseModel):
    lifter: str
    filename: str
    uploaded_at: datetime
    sheets: list[SheetSummary]
    skipped_sheets: list[str]
    note_count: int
    issues: list[ProgramIssueOut]
    rows: list[ProgramRowOut]


def _program_response(upload: Upload) -> ProgramResponse:
    """The stored program, newest block first."""
    sheets: dict[str, SheetSummary] = {}
    rows: list[ProgramRowOut] = []
    note_count = 0
    for block in reversed(upload.blocks):
        summary = sheets.setdefault(
            block.sheet_name,
            SheetSummary(
                name=block.sheet_name, blocks=0, weeks=0, lines=0, first_week=None, last_week=None
            ),
        )
        summary.blocks += 1
        for week in block.weeks:
            summary.weeks += 1
            summary.lines += len(week.rows)
            note_count += len(week.notes)
            if week.start_date:
                summary.first_week = min(summary.first_week or week.start_date, week.start_date)
                summary.last_week = max(summary.last_week or week.start_date, week.start_date)
            rows.extend(
                ProgramRowOut(
                    id=row.id,
                    block_index=block.block_index,
                    sheet=block.sheet_name,
                    cell=row.sheet_cell,
                    week_number=week.week_number,
                    week_label=week.label,
                    week_start=week.start_date,
                    day_label=row.day_label,
                    movement=row.movement_raw,
                    lift=row.lift,
                    variation=row.variation,
                    sets=row.sets,
                    reps_raw=row.reps_raw,
                    intensity_raw=row.intensity_raw,
                    target_load_raw=row.target_load_raw,
                    actual_load_raw=row.load_raw,
                    actual_load_kg=row.load_kg,
                    rpe=row.rpe,
                    rpe_below_5=row.rpe_below_5,
                    assumed_kg=row.assumed_kg,
                )
                for row in week.rows
            )
    return ProgramResponse(
        lifter=upload.lifter.name,
        filename=upload.filename,
        uploaded_at=upload.uploaded_at,
        sheets=list(sheets.values()),
        skipped_sheets=upload.skipped_sheets,
        note_count=note_count,
        issues=[
            ProgramIssueOut(sheet=issue.sheet, cell=issue.cell, message=issue.message)
            for issue in upload.issues
        ],
        rows=rows,
    )


@app.post("/api/program/upload")
def upload_program(
    file: UploadFile, session: DbSession, lifter: str = DEFAULT_LIFTER
) -> ProgramResponse:
    """Parse an uploaded coach spreadsheet and store it, replacing the lifter's previous one."""
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 20 MB.")
    try:
        result = parse_workbook(BytesIO(content))
    except (BadZipFile, InvalidFileException, KeyError, OSError) as error:
        detail = "Could not read this file as an Excel workbook (.xlsx)."
        raise HTTPException(status_code=400, detail=detail) from error
    if not result.rows:
        detail = "No program lines found. Is this the coach's program spreadsheet?"
        raise HTTPException(status_code=400, detail=detail)
    upload = store_program(session, lifter, file.filename or "program.xlsx", result)
    session.commit()
    return _program_response(upload)


@app.get("/api/program")
def get_program(session: DbSession, lifter: str = DEFAULT_LIFTER) -> ProgramResponse:
    upload = latest_upload(session, lifter)
    if upload is None:
        raise HTTPException(status_code=404, detail="No program uploaded yet.")
    return _program_response(upload)


@cache
def get_chat_model() -> ChatModel:
    """The assistant's model. Swap the provider here."""
    return OllamaModel()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    lifter: str = DEFAULT_LIFTER


class CalculationOut(BaseModel):
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]


class AssistantResponse(BaseModel):
    status: Literal["answered", "needs_clarification", "referred"]
    answer: str
    basis_set: dict[str, Any] | None
    calculations: list[CalculationOut]
    flags: list[str]


@app.post("/api/assistant/ask")
def ask_assistant(
    request: AskRequest,
    session: DbSession,
    model: Annotated[ChatModel, Depends(get_chat_model)],
) -> AssistantResponse:
    """Answer a question about the lifter's stored program. Numbers come only from tools."""
    assistant = Assistant(model, ProgramTools(session, request.lifter))
    try:
        answer = assistant.ask(request.question)
    except ModelUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return AssistantResponse(
        status=answer.status,
        answer=answer.answer,
        basis_set=answer.basis_set,
        calculations=[
            CalculationOut(tool=calc.tool, arguments=calc.arguments, result=calc.result)
            for calc in answer.calculations
        ],
        flags=answer.flags,
    )
