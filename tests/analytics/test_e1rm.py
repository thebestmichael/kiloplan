import pytest

from kiloplan.analytics.e1rm import brzycki, e1rm_from_rpe, epley, hybrid


@pytest.mark.parametrize(
    ("weight_kg", "reps", "expected"),
    [
        (100, 1, 100.0),
        (100, 5, 116.6667),
        (100, 10, 133.3333),
        (142.5, 3, 156.75),
    ],
)
def test_epley(weight_kg, reps, expected):
    assert epley(weight_kg, reps) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize(
    ("weight_kg", "reps", "expected"),
    [
        (100, 1, 100.0),
        (100, 5, 112.5),
        (100, 10, 133.3333),
        (142.5, 3, 150.8824),
    ],
)
def test_brzycki(weight_kg, reps, expected):
    assert brzycki(weight_kg, reps) == pytest.approx(expected, abs=1e-4)


def test_brzycki_rejects_reps_above_limit():
    assert brzycki(100, 36) == pytest.approx(3600.0)
    with pytest.raises(ValueError, match="at most 36"):
        brzycki(100, 37)


@pytest.mark.parametrize("formula", [epley, brzycki])
@pytest.mark.parametrize(("weight_kg", "reps"), [(0, 5), (-20, 5), (100, 0), (100, -1)])
def test_formulas_reject_invalid_input(formula, weight_kg, reps):
    with pytest.raises(ValueError):
        formula(weight_kg, reps)


@pytest.mark.parametrize(
    ("weight_kg", "reps", "rpe", "expected"),
    [
        (100, 5, 10, 116.6667),  # no reps in reserve: plain Epley
        (100, 5, 8, 123.3333),  # 2 in reserve: Epley at 7 reps
        (100, 3, 8.5, 115.0),  # 1.5 in reserve: Epley at 4.5 reps
        (100, 1, 10, 100.0),
    ],
)
def test_e1rm_from_rpe_with_epley(weight_kg, reps, rpe, expected):
    assert e1rm_from_rpe(weight_kg, reps, rpe, formula=epley) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize(
    ("weight_kg", "reps", "expected"),
    [
        (100, 1, 100.0),  # Brzycki side
        (100, 5, 112.5),
        (100, 10, 133.3333),  # switch point: both formulas agree
        (100, 10.5, 135.0),  # Epley side
        (100, 12, 140.0),
    ],
)
def test_hybrid(weight_kg, reps, expected):
    assert hybrid(weight_kg, reps) == pytest.approx(expected, abs=1e-4)


def test_hybrid_is_continuous_at_switch():
    assert hybrid(100, 10) == pytest.approx(hybrid(100, 10.001), abs=0.01)
    assert brzycki(100, 10) == pytest.approx(epley(100, 10))


def test_hybrid_handles_reps_beyond_brzycki_limit():
    assert hybrid(100, 40) == pytest.approx(epley(100, 40))


def test_e1rm_from_rpe_defaults_to_hybrid():
    # 5 reps @ RPE 8 = 7 theoretical reps: Brzycki
    assert e1rm_from_rpe(100, 5, 8) == pytest.approx(120.0)
    # 8 reps @ RPE 6 = 12 theoretical reps: Epley
    assert e1rm_from_rpe(100, 8, 6) == pytest.approx(140.0)


def test_e1rm_from_rpe_with_brzycki():
    # 2 in reserve: Brzycki at 7 reps = 100 * 36 / 30
    assert e1rm_from_rpe(100, 5, 8, formula=brzycki) == pytest.approx(120.0)


@pytest.mark.parametrize("rpe", [0, 0.5, 10.5, 11])
def test_e1rm_from_rpe_rejects_out_of_range_rpe(rpe):
    with pytest.raises(ValueError, match="rpe must be between"):
        e1rm_from_rpe(100, 5, rpe)
