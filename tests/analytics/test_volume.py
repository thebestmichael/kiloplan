import pytest

from kiloplan.analytics.volume import volume_kg, weekly_volume


def test_volume_is_sets_times_reps_times_load():
    assert volume_kg(3, 5, 100) == 1500
    assert volume_kg(1, 1, 182.5) == 182.5
    assert volume_kg(0, 5, 100) == 0


@pytest.mark.parametrize("line", [(-1, 5, 100), (3, -5, 100), (3, 5, -100)])
def test_volume_rejects_negative_values(line):
    with pytest.raises(ValueError):
        volume_kg(*line)


def test_weekly_volume_totals_each_lift_in_each_week():
    lines = [
        (1, "squat", 1, 3, 180.0),
        (1, "squat", 3, 5, 160.0),
        (1, "bench", 3, 5, 100.0),
        (2, "squat", 1, 2, 190.0),
    ]
    assert weekly_volume(lines) == {
        (1, "squat"): 540 + 2400,
        (1, "bench"): 1500,
        (2, "squat"): 380,
    }
    assert weekly_volume([]) == {}
