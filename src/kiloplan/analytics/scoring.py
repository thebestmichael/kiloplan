"""Powerlifting points formulas: Wilks, Wilks 2020, DOTS and IPF GL. Weights in kg.

Coefficients and bodyweight bounds follow the OpenPowerlifting implementation.
Bodyweights outside a formula's range score as the nearest bound.
"""

from math import exp
from typing import Literal

Sex = Literal["male", "female"]

MIN_GL_BODYWEIGHT_KG = 35.0

# polynomial coefficients, constant term first
WILKS = {
    "male": (-216.0475144, 16.2606339, -0.002388645, -0.00113732, 7.01863e-06, -1.291e-08),
    "female": (
        594.31747775582,
        -27.23842536447,
        0.82112226871,
        -0.00930733913,
        0.00004731582,
        -0.00000009054,
    ),
}
WILKS_BOUNDS = {"male": (40.0, 201.9), "female": (26.51, 154.53)}

WILKS_2020 = {
    "male": (
        47.4617885411949,
        8.47206137941125,
        0.073694103462609,
        -0.00139583381094385,
        0.00000707665973070743,
        -0.0000000120804336482315,
    ),
    "female": (
        -125.425539779509,
        13.7121941940668,
        -0.0330725063103405,
        -0.0010504000506583,
        0.00000938773881462799,
        -0.000000023334613884954,
    ),
}
WILKS_2020_BOUNDS = {"male": (40.0, 200.95), "female": (40.0, 150.95)}

DOTS = {
    "male": (-307.75076, 24.0900756, -0.1918759221, 0.0007391293, -0.0000010930),
    "female": (-57.96288, 13.6175032, -0.1126655495, 0.0005158568, -0.0000010706),
}
DOTS_BOUNDS = {"male": (40.0, 210.0), "female": (40.0, 150.0)}

# IPF GL parameters (A, B, C) by (sex, equipped, bench_only)
IPF_GL = {
    ("male", False, False): (1199.72839, 1025.18162, 0.009210),
    ("male", True, False): (1236.25115, 1449.21864, 0.01644),
    ("female", False, False): (610.32796, 1045.59282, 0.03048),
    ("female", True, False): (758.63878, 949.31382, 0.02435),
    ("male", False, True): (320.98041, 281.40258, 0.01008),
    ("male", True, True): (381.22073, 733.79378, 0.02398),
    ("female", False, True): (142.40398, 442.52671, 0.04724),
    ("female", True, True): (221.82209, 357.00377, 0.02937),
}


def _validate(bodyweight_kg: float, total_kg: float) -> None:
    if bodyweight_kg <= 0:
        raise ValueError(f"bodyweight_kg must be positive, got {bodyweight_kg}")
    if total_kg < 0:
        raise ValueError(f"total_kg cannot be negative, got {total_kg}")


def _polynomial(coefficients: tuple[float, ...], x: float) -> float:
    return sum(coefficient * x**power for power, coefficient in enumerate(coefficients))


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return min(max(value, bounds[0]), bounds[1])


def wilks_coefficient(sex: Sex, bodyweight_kg: float) -> float:
    return 500 / _polynomial(WILKS[sex], _clamp(bodyweight_kg, WILKS_BOUNDS[sex]))


def wilks(sex: Sex, bodyweight_kg: float, total_kg: float) -> float:
    """Original Wilks points."""
    _validate(bodyweight_kg, total_kg)
    return total_kg * wilks_coefficient(sex, bodyweight_kg)


def wilks_2020_coefficient(sex: Sex, bodyweight_kg: float) -> float:
    return 600 / _polynomial(WILKS_2020[sex], _clamp(bodyweight_kg, WILKS_2020_BOUNDS[sex]))


def wilks_2020(sex: Sex, bodyweight_kg: float, total_kg: float) -> float:
    """Wilks points with the 2020 coefficients."""
    _validate(bodyweight_kg, total_kg)
    return total_kg * wilks_2020_coefficient(sex, bodyweight_kg)


def dots_coefficient(sex: Sex, bodyweight_kg: float) -> float:
    return 500 / _polynomial(DOTS[sex], _clamp(bodyweight_kg, DOTS_BOUNDS[sex]))


def dots(sex: Sex, bodyweight_kg: float, total_kg: float) -> float:
    """DOTS points."""
    _validate(bodyweight_kg, total_kg)
    return total_kg * dots_coefficient(sex, bodyweight_kg)


def ipf_gl(
    sex: Sex,
    bodyweight_kg: float,
    total_kg: float,
    equipped: bool = False,
    bench_only: bool = False,
) -> float:
    """IPF GL (Goodlift) points. Zero below 35 kg bodyweight, where the formula is undefined."""
    _validate(bodyweight_kg, total_kg)
    if bodyweight_kg < MIN_GL_BODYWEIGHT_KG:
        return 0.0
    a, b, c = IPF_GL[sex, equipped, bench_only]
    return total_kg * max(0.0, 100 / (a - b * exp(-c * bodyweight_kg)))
