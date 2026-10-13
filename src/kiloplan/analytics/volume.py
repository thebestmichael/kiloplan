"""Training volume. All weights in kg."""

from collections import defaultdict
from collections.abc import Hashable, Iterable


def volume_kg(sets: int, reps: int, load_kg: float) -> float:
    """Tonnage of one program line: sets x reps x load."""
    if sets < 0 or reps < 0 or load_kg < 0:
        raise ValueError("sets, reps and load_kg cannot be negative")
    return sets * reps * load_kg


def weekly_volume[Week: Hashable](
    lines: Iterable[tuple[Week, str, int, int, float]],
) -> dict[tuple[Week, str], float]:
    """Total tonnage per (week, lift) from lines of (week, lift, sets, reps, load_kg)."""
    totals: dict[tuple[Week, str], float] = defaultdict(float)
    for week, lift, sets, reps, load_kg in lines:
        totals[week, lift] += volume_kg(sets, reps, load_kg)
    return dict(totals)
