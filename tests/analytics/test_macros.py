import pytest

from kiloplan.analytics.nutrition import (
    Macros,
    for_grams,
    kcal_from_macros,
    recommended_water_ml,
    remaining,
    total,
)


def test_for_grams_scales_per_100g_values():
    chicken = Macros(kcal=165, protein_g=31, carbs_g=0, fat_g=3.6)
    assert for_grams(chicken, 150) == Macros(247.5, 46.5, 0, pytest.approx(5.4))
    assert for_grams(chicken, 0) == Macros()
    with pytest.raises(ValueError):
        for_grams(chicken, -1)


def test_total_and_remaining():
    eaten = total([Macros(500, 40, 50, 15), Macros(300, 10, 45, 8)])
    assert eaten == Macros(800, 50, 95, 23)
    assert total([]) == Macros()
    # going past a goal leaves a negative amount
    assert remaining(Macros(2500, 180, 300, 70), eaten) == Macros(1700, 130, 205, 47)
    assert remaining(Macros(700, 60, 80, 20), eaten) == Macros(-100, 10, -15, -3)


def test_kcal_from_macros_uses_4_4_9():
    assert kcal_from_macros(protein_g=30, carbs_g=50, fat_g=10) == 410


def test_recommended_water_is_35_ml_per_kg():
    assert recommended_water_ml(80) == 2800
    assert recommended_water_ml(100.5) == pytest.approx(3517.5)
    with pytest.raises(ValueError):
        recommended_water_ml(0)
