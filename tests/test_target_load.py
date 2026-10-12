import pytest

from kiloplan.analytics.e1rm import (
    brzycki,
    brzycki_weight,
    epley,
    epley_weight,
    hybrid,
    hybrid_weight,
    round_to_increment,
    target_weight_from_pr,
    weight_for_rpe,
)


@pytest.mark.parametrize(
    ("formula", "inverse"),
    [(epley, epley_weight), (brzycki, brzycki_weight), (hybrid, hybrid_weight)],
)
@pytest.mark.parametrize(("weight_kg", "reps"), [(100, 1), (100, 5), (142.5, 3), (60, 12)])
def test_inverse_round_trips(formula, inverse, weight_kg, reps):
    assert inverse(formula(weight_kg, reps), reps) == pytest.approx(weight_kg)


def test_epley_weight_known_value():
    assert epley_weight(120, 6) == pytest.approx(100.0)


def test_brzycki_weight_known_value():
    assert brzycki_weight(112.5, 5) == pytest.approx(100.0)


def test_brzycki_weight_rejects_reps_above_limit():
    with pytest.raises(ValueError, match="at most 36"):
        brzycki_weight(100, 37)


def test_weight_for_rpe():
    # triple at RPE 8 has 2 in reserve: Epley weight at 5 reps = 140 / (1 + 5/30)
    assert weight_for_rpe(140, 3, 8, inverse=epley_weight) == pytest.approx(120.0)
    assert weight_for_rpe(140, 1, 10, inverse=epley_weight) == pytest.approx(140.0)


def test_weight_for_rpe_defaults_to_hybrid():
    # triple at RPE 8 = 5 theoretical reps: Brzycki weight = 144 * 32 / 36
    assert weight_for_rpe(144, 3, 8) == pytest.approx(128.0)
    # 8 reps at RPE 6 = 12 theoretical reps: Epley weight = 140 / 1.4
    assert weight_for_rpe(140, 8, 6) == pytest.approx(100.0)


def test_target_weight_from_pr_with_epley():
    # PR triple 180 @ RPE 9 -> e1RM 180 * (1 + 4/30) = 204
    # target triple @ RPE 5 -> 204 / (1 + 8/30)
    result = target_weight_from_pr(180, 3, 9, 3, 5, formula=epley, inverse=epley_weight)
    assert result == pytest.approx(161.0526, abs=1e-4)


def test_target_weight_from_pr_defaults_to_hybrid():
    # both sets are under 10 theoretical reps, so this matches Brzycki
    assert target_weight_from_pr(180, 3, 9, 3, 5) == pytest.approx(158.1818, abs=1e-4)


def test_target_weight_from_pr_across_hybrid_switch():
    # top set 3 @ RPE 9 (4 theoretical reps, Brzycki): e1RM = 180 * 36 / 33
    # backdown 8 @ RPE 6 (12 theoretical reps, Epley): e1RM / 1.4
    assert target_weight_from_pr(180, 3, 9, 8, 6) == pytest.approx(140.2597, abs=1e-4)


def test_target_weight_from_pr_same_set_returns_pr_weight():
    assert target_weight_from_pr(180, 3, 9, 3, 9) == pytest.approx(180.0)


def test_target_weight_from_pr_with_brzycki():
    # e1RM = 180 * 36 / 33; target = e1RM * (37 - 8) / 36
    result = target_weight_from_pr(180, 3, 9, 3, 5, formula=brzycki, inverse=brzycki_weight)
    assert result == pytest.approx(158.1818, abs=1e-4)


@pytest.mark.parametrize("rpe", [0, 10.5])
def test_target_weight_rejects_out_of_range_rpe(rpe):
    with pytest.raises(ValueError, match="rpe must be between"):
        target_weight_from_pr(180, 3, 9, 3, rpe)
    with pytest.raises(ValueError, match="rpe must be between"):
        target_weight_from_pr(180, 3, rpe, 3, 5)


@pytest.mark.parametrize(
    ("weight_kg", "increment_kg", "expected"),
    [(161.05, 2.5, 160.0), (161.3, 2.5, 162.5), (161.05, 1.0, 161.0), (158.2, 5.0, 160.0)],
)
def test_round_to_increment(weight_kg, increment_kg, expected):
    assert round_to_increment(weight_kg, increment_kg) == pytest.approx(expected)


def test_round_to_increment_rejects_non_positive_increment():
    with pytest.raises(ValueError):
        round_to_increment(100, 0)
