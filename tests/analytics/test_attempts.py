import pytest

from kiloplan.analytics.attempts import select_attempts
from kiloplan.analytics.e1rm import rep_max_table, rpe_chart


@pytest.mark.parametrize(
    ("goal_kg", "expected"),
    [
        (200, (182.5, 192.5, 200.0)),  # 182, 192 and 200 on 2.5 kg jumps
        (142.5, (130.0, 137.5, 142.5)),
        (267.5, (242.5, 257.5, 267.5)),
        (101, (92.5, 97.5, 100.0)),  # the goal itself is rounded to a loadable weight
    ],
)
def test_select_attempts(goal_kg, expected):
    assert select_attempts(goal_kg) == expected


def test_select_attempts_with_a_smaller_increment():
    assert select_attempts(60, increment_kg=0.5) == (54.5, 57.5, 60.0)


def test_select_attempts_rejects_a_non_positive_goal():
    with pytest.raises(ValueError):
        select_attempts(0)


def test_rep_max_table():
    table = rep_max_table(200)
    assert list(table) == list(range(1, 11))
    assert table[1] == pytest.approx(200)
    # Brzycki inverse: 200 * (37 - reps) / 36
    assert table[5] == pytest.approx(177.7778, abs=1e-4)
    assert table[10] == pytest.approx(150)
    assert all(table[reps] > table[reps + 1] for reps in range(1, 10))


def test_rpe_chart():
    chart = rpe_chart(200)
    assert list(chart) == [10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5, 6]
    # the RPE 10 row is the rep max table
    assert chart[10] == rep_max_table(200)
    # 3 reps at RPE 8 = 5 theoretical reps
    assert chart[8][3] == pytest.approx(rep_max_table(200)[5])
    # 8 reps at RPE 6 = 12 theoretical reps, past the switch to Epley: 200 / 1.4
    assert chart[6][8] == pytest.approx(142.8571, abs=1e-4)
