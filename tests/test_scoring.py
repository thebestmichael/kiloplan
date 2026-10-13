import pytest

from kiloplan.analytics.scoring import (
    dots,
    dots_coefficient,
    ipf_gl,
    total_for_points,
    wilks,
    wilks_2020,
    wilks_2020_coefficient,
    wilks_coefficient,
)

# Expected values are the published check values used by OpenPowerlifting's tests.


def test_wilks_coefficients():
    assert wilks_coefficient("male", 100) == pytest.approx(0.6085890719066511)
    assert wilks_coefficient("female", 100) == pytest.approx(0.8325833167368228)


def test_wilks_points():
    assert wilks("male", 100, 1000) == pytest.approx(608.58907, abs=1e-4)
    assert wilks("female", 60, 500) == pytest.approx(557.4434, abs=1e-4)


@pytest.mark.parametrize(
    ("bodyweight_kg", "expected"),
    [(40, 1.3895), (60, 0.9968), (80, 0.8191), (100, 0.7294), (140, 0.6546), (200.95, 0.6122)],
)
def test_wilks_2020_coefficients_men(bodyweight_kg, expected):
    assert wilks_2020_coefficient("male", bodyweight_kg) == pytest.approx(expected, abs=5e-5)


@pytest.mark.parametrize(
    ("bodyweight_kg", "expected"),
    [(40, 1.8486), (60, 1.3190), (80, 1.1318), (100, 1.0525), (150.95, 0.9627)],
)
def test_wilks_2020_coefficients_women(bodyweight_kg, expected):
    assert wilks_2020_coefficient("female", bodyweight_kg) == pytest.approx(expected, abs=5e-5)


def test_bodyweights_outside_a_formulas_range_use_the_nearest_bound():
    assert wilks_2020_coefficient("male", 20) == wilks_2020_coefficient("male", 40)
    assert wilks_2020_coefficient("male", 400) == wilks_2020_coefficient("male", 200.95)
    assert dots_coefficient("male", 250) == dots_coefficient("male", 210)
    assert dots_coefficient("female", 30) == dots_coefficient("female", 40)
    assert wilks_coefficient("female", 200) == wilks_coefficient("female", 154.53)


def test_dots_points():
    # 500 / (-307.75076 + 24.0900756*100 - 0.1918759221*100^2 + 0.0007391293*100^3
    #        - 0.000001093*100^4) = 500 / 812.326879
    assert dots_coefficient("male", 100) == pytest.approx(500 / 812.326879, rel=1e-7)
    assert dots("male", 100, 800) == pytest.approx(492.41, abs=0.01)
    assert dots("female", 60, 400) == pytest.approx(400 * dots_coefficient("female", 60))
    assert dots_coefficient("female", 60) > dots_coefficient("male", 60)


def test_ipf_gl_published_examples():
    # Dmitry Inzarkin, 2019 IPF World Open Men's Championships (equipped)
    assert ipf_gl("male", 92.04, 1035, equipped=True) == pytest.approx(112.85, abs=0.005)
    # Susanna Torronen, 2019 World Open Classic Bench Press Championships
    assert ipf_gl("female", 70.5, 122.5, bench_only=True) == pytest.approx(96.78, abs=0.005)


def test_ipf_gl_is_zero_below_its_bodyweight_floor():
    assert ipf_gl("male", 30, 300) == 0


def test_points_scale_with_the_total():
    for formula in (wilks, wilks_2020, dots, ipf_gl):
        assert formula("male", 90, 0) == 0
        assert formula("male", 90, 600) == pytest.approx(2 * formula("male", 90, 300))


@pytest.mark.parametrize("formula", [wilks, wilks_2020, dots, ipf_gl])
def test_points_reject_invalid_input(formula):
    with pytest.raises(ValueError):
        formula("male", 0, 500)
    with pytest.raises(ValueError):
        formula("male", 90, -5)


@pytest.mark.parametrize(
    ("formula", "score"),
    [("dots", dots), ("wilks", wilks), ("wilks_2020", wilks_2020), ("ipf_gl", ipf_gl)],
)
def test_total_for_points_is_the_inverse_of_each_formula(formula, score):
    for sex, bodyweight_kg, total_kg in (("male", 93, 702.5), ("female", 63, 410)):
        points = score(sex, bodyweight_kg, total_kg)
        assert total_for_points(formula, sex, bodyweight_kg, points) == pytest.approx(total_kg)


def test_total_for_points_known_values():
    # Wilks coefficient for a 100 kg man is 0.6085890719, so 500 points needs 500 / 0.60859
    assert total_for_points("wilks", "male", 100, 500) == pytest.approx(821.57, abs=0.01)
    # the published IPF GL examples, run backwards
    equipped = total_for_points("ipf_gl", "male", 92.04, 112.85, equipped=True)
    assert equipped == pytest.approx(1035, abs=0.05)
    bench = total_for_points("ipf_gl", "female", 70.5, 96.78, bench_only=True)
    assert bench == pytest.approx(122.5, abs=0.01)
    assert total_for_points("dots", "male", 90, 0) == 0


def test_total_for_points_rejects_what_cannot_be_answered():
    with pytest.raises(ValueError, match="not defined"):
        total_for_points("ipf_gl", "male", 30, 100)
    with pytest.raises(ValueError):
        total_for_points("dots", "male", 90, -10)
    with pytest.raises(ValueError):
        total_for_points("dots", "male", 0, 400)
