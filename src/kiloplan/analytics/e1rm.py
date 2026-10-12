"""Estimated one-rep max (e1RM) formulas. All weights in kg."""

from collections.abc import Callable

E1rmFormula = Callable[[float, float], float]

BRZYCKI_MAX_REPS = 36
# Brzycki and Epley give the same estimate at 10 reps, so switching there is continuous.
HYBRID_SWITCH_REPS = 10
MIN_RPE = 1.0
MAX_RPE = 10.0


def _validate(weight_kg: float, reps: float) -> None:
    if weight_kg <= 0:
        raise ValueError(f"weight_kg must be positive, got {weight_kg}")
    if reps < 1:
        raise ValueError(f"reps must be at least 1, got {reps}")


def _validate_rpe(rpe: float) -> None:
    if not MIN_RPE <= rpe <= MAX_RPE:
        raise ValueError(f"rpe must be between {MIN_RPE} and {MAX_RPE}, got {rpe}")


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


def epley_weight(e1rm_kg: float, reps: float) -> float:
    """Inverse of epley: the weight that gives this e1RM at the given reps."""
    _validate(e1rm_kg, reps)
    if reps == 1:
        return e1rm_kg
    return e1rm_kg / (1 + reps / 30)


def brzycki_weight(e1rm_kg: float, reps: float) -> float:
    """Inverse of brzycki: the weight that gives this e1RM at the given reps."""
    _validate(e1rm_kg, reps)
    if reps > BRZYCKI_MAX_REPS:
        raise ValueError(f"brzycki supports at most {BRZYCKI_MAX_REPS} reps, got {reps}")
    return e1rm_kg * (37 - reps) / 36


def hybrid(weight_kg: float, reps: float) -> float:
    """Brzycki up to 10 reps, Epley above."""
    if reps <= HYBRID_SWITCH_REPS:
        return brzycki(weight_kg, reps)
    return epley(weight_kg, reps)


def hybrid_weight(e1rm_kg: float, reps: float) -> float:
    """Inverse of hybrid: the weight that gives this e1RM at the given reps."""
    if reps <= HYBRID_SWITCH_REPS:
        return brzycki_weight(e1rm_kg, reps)
    return epley_weight(e1rm_kg, reps)


def e1rm_from_rpe(
    weight_kg: float, reps: float, rpe: float, formula: E1rmFormula = hybrid
) -> float:
    """Estimate 1RM from a submaximal set by adding reps in reserve (10 - RPE) to reps."""
    _validate_rpe(rpe)
    return formula(weight_kg, reps + (MAX_RPE - rpe))


def weight_for_rpe(
    e1rm_kg: float, reps: float, rpe: float, inverse: E1rmFormula = hybrid_weight
) -> float:
    """Weight to load for a set of `reps` at the target RPE, given an e1RM."""
    _validate_rpe(rpe)
    return inverse(e1rm_kg, reps + (MAX_RPE - rpe))


def target_weight_from_pr(
    pr_weight_kg: float,
    pr_reps: float,
    pr_rpe: float,
    target_reps: float,
    target_rpe: float,
    formula: E1rmFormula = hybrid,
    inverse: E1rmFormula = hybrid_weight,
) -> float:
    """Weight for a target set, derived from a past set of the same lift variation.

    `formula` and `inverse` must be a matching pair, e.g. epley/epley_weight.
    """
    e1rm_kg = e1rm_from_rpe(pr_weight_kg, pr_reps, pr_rpe, formula)
    return weight_for_rpe(e1rm_kg, target_reps, target_rpe, inverse)


def round_to_increment(weight_kg: float, increment_kg: float = 2.5) -> float:
    """Round to the nearest loadable weight, e.g. 2.5 kg jumps."""
    if increment_kg <= 0:
        raise ValueError(f"increment_kg must be positive, got {increment_kg}")
    return round(weight_kg / increment_kg) * increment_kg
