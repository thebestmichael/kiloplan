"""FastAPI app. Run with: uv run uvicorn kiloplan.api.main:app --reload"""

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from kiloplan.analytics.e1rm import (
    MAX_RPE,
    MIN_RPE,
    brzycki,
    brzycki_weight,
    e1rm_from_rpe,
    epley,
    epley_weight,
    round_to_increment,
    weight_for_rpe,
)

app = FastAPI(title="KiloPlan")

FORMULAS = {
    "epley": (epley, epley_weight),
    "brzycki": (brzycki, brzycki_weight),
}


class TargetLoadRequest(BaseModel):
    pr_weight_kg: float = Field(gt=0)
    pr_reps: int = Field(ge=1)
    pr_rpe: float = Field(ge=MIN_RPE, le=MAX_RPE)
    target_reps: int = Field(ge=1)
    target_rpe: float = Field(ge=MIN_RPE, le=MAX_RPE)
    formula: Literal["epley", "brzycki"] = "epley"
    increment_kg: float = Field(default=2.5, gt=0)


class TargetLoadResponse(BaseModel):
    e1rm_kg: float
    target_weight_kg: float
    rounded_weight_kg: float


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
    return TargetLoadResponse(
        e1rm_kg=e1rm_kg,
        target_weight_kg=target_weight_kg,
        rounded_weight_kg=round_to_increment(target_weight_kg, request.increment_kg),
    )
