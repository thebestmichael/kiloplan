"""Barbell plate loading. Works in whatever unit the plates are in (kg or lb)."""

from dataclasses import dataclass
from functools import reduce
from math import gcd

# weights are handled as whole thousandths so plate sums are exact
SCALE = 1000


@dataclass(frozen=True)
class PlateLoad:
    """`per_side` is heaviest first. `shortfall` is how far the bar ends up under the target."""

    per_side: tuple[float, ...]
    total: float
    shortfall: float


def bar_total(per_side: list[float], bar: float, collar: float = 0.0) -> float:
    """Total weight of a bar loaded with these plates on each side."""
    if bar < 0 or collar < 0 or any(plate <= 0 for plate in per_side):
        raise ValueError("bar, collar and plate weights cannot be negative")
    return bar + 2 * collar + 2 * sum(per_side)


def load_bar(target: float, bar: float, plates: dict[float, int], collar: float = 0.0) -> PlateLoad:
    """Plates per side that get closest to `target` without going over.

    `plates` maps a plate weight to how many pairs are available. Among loads that
    reach the same total, the one using the fewest plates is chosen, then the one
    with the heaviest plates.
    """
    if bar < 0 or collar < 0:
        raise ValueError("bar and collar weights cannot be negative")
    if any(weight <= 0 or pairs < 0 for weight, pairs in plates.items()):
        raise ValueError("plate weights must be positive and pair counts cannot be negative")
    empty = bar + 2 * collar
    if target < empty:
        raise ValueError(f"target {target:g} is below the empty bar ({empty:g})")

    available = [round(weight * SCALE) for weight, pairs in plates.items() for _ in range(pairs)]
    if not available:
        return PlateLoad((), empty, target - empty)
    step = reduce(gcd, available)
    capacity = int((target - empty) / 2 * SCALE + 1e-6) // step

    # best[w] is the way to put exactly w steps on one side: fewest plates, and among
    # those the heaviest plates. Plates are added heaviest first, so tuples stay sorted.
    best: list[tuple[int, ...] | None] = [None] * (capacity + 1)
    best[0] = ()
    for plate in sorted(available, reverse=True):
        size = plate // step
        for load in range(capacity, size - 1, -1):
            lighter = best[load - size]
            if lighter is None:
                continue
            candidate = (*lighter, plate)
            current = best[load]
            if current is None or (len(candidate), current) < (len(current), candidate):
                best[load] = candidate

    chosen = next(combination for combination in reversed(best) if combination is not None)
    per_side = tuple(sorted((plate / SCALE for plate in chosen), reverse=True))
    total = empty + 2 * sum(per_side)
    return PlateLoad(per_side, total, target - total)
