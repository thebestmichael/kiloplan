"""Macro arithmetic for the food diary. Energy in kcal, macros in grams."""

from collections.abc import Iterable
from dataclasses import dataclass

# A common rule of thumb for daily fluid: about 35 ml per kg of bodyweight. It is a
# starting point, not a limit, and not medical advice.
WATER_ML_PER_KG = 35.0


@dataclass(frozen=True)
class Macros:
    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0

    def __add__(self, other: "Macros") -> "Macros":
        return Macros(
            self.kcal + other.kcal,
            self.protein_g + other.protein_g,
            self.carbs_g + other.carbs_g,
            self.fat_g + other.fat_g,
        )

    def __sub__(self, other: "Macros") -> "Macros":
        return Macros(
            self.kcal - other.kcal,
            self.protein_g - other.protein_g,
            self.carbs_g - other.carbs_g,
            self.fat_g - other.fat_g,
        )


def for_grams(per_100g: Macros, grams: float) -> Macros:
    """Macros in `grams` of a food whose values are given per 100 g."""
    if grams < 0:
        raise ValueError(f"grams cannot be negative, got {grams}")
    share = grams / 100
    return Macros(
        per_100g.kcal * share,
        per_100g.protein_g * share,
        per_100g.carbs_g * share,
        per_100g.fat_g * share,
    )


def total(items: Iterable[Macros]) -> Macros:
    return sum(items, Macros())


def remaining(goal: Macros, eaten: Macros) -> Macros:
    """What is left of a daily goal. Negative values mean the goal was passed."""
    return goal - eaten


def kcal_from_macros(protein_g: float, carbs_g: float, fat_g: float) -> float:
    """Energy by the 4/4/9 rule, for foods with no energy value."""
    return 4 * protein_g + 4 * carbs_g + 9 * fat_g


def recommended_water_ml(bodyweight_kg: float) -> float:
    """A suggested daily water intake for a bodyweight."""
    if bodyweight_kg <= 0:
        raise ValueError(f"bodyweight_kg must be positive, got {bodyweight_kg}")
    return WATER_ML_PER_KG * bodyweight_kg
