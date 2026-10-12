"""Estimated one-rep max (e1RM) formulas. All weights in kg."""

from collections.abc import Callable

E1rmFormula = Callable[[float, float], float]

BRZYCKI_MAX_REPS = 36
MIN_RPE = 1.0
MAX_RPE = 10.0


def _validate(weight_kg: float, reps: float) -> None:
    if weight_kg <= 0:
        raise ValueError(f"weight_kg must be positive, got {weight_kg}")
    if reps < 1:
        raise ValueError(f"reps must be at least 1, got {reps}")


def epley(weight_kg: float, reps: float) -> float:
    """Epley estimate: weight * (1 + reps / 30). A single rep is its own 1RM."""
    _validate(weight_kg, reps)
    if reps == 1:
        return weight_kg
    return weight_kg * (1 + reps / 30)


def brzycki(weight_kg: float, reps: float) -> float:
    """Brzycki estimate: weight * 36 / (37 - reps). Undefined above 36 reps."""
    _validate(weight_kg, reps)
    if reps > BRZYCKI_MAX_REPS:
        raise ValueError(f"brzycki supports at most {BRZYCKI_MAX_REPS} reps, got {reps}")
    return weight_kg * 36 / (37 - reps)


def e1rm_from_rpe(weight_kg: float, reps: float, rpe: float, formula: E1rmFormula = epley) -> float:
    """Estimate 1RM from a submaximal set by adding reps in reserve (10 - RPE) to reps."""
    if not MIN_RPE <= rpe <= MAX_RPE:
        raise ValueError(f"rpe must be between {MIN_RPE} and {MAX_RPE}, got {rpe}")
    return formula(weight_kg, reps + (MAX_RPE - rpe))
