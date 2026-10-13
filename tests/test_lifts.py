import pytest

from kiloplan.ingestion.lifts import classify


@pytest.mark.parametrize(
    ("movement", "lift", "variation"),
    [
        ("Squat", "squat", "competition"),
        ("Squats", "squat", "competition"),
        ("Comp Deadlifts ", "deadlift", "competition"),
        ("Comp Bench", "bench", "competition"),
        ("Paused Squats", "squat", "paused"),
        ("Pause Squat", "squat", "paused"),
        ("2ct paused deadlifts", "deadlift", "2ct paused"),
        ("3Ct pause Bench", "bench", "3ct paused"),
        ("4-2-0 Tempo bench", "bench", "4-2-0 tempo"),
        ("Close Grip Bench", "bench", "close grip"),
        ("SSB Squats", "squat", "ssb"),
        ("Stiff Leg Deadlifts", "deadlift", "stiff leg"),
        ("Spoto Press", "bench", "spoto"),
        ("Spotto Press", "bench", "spoto"),
        ("Larsen Press", "bench", "larsen"),
    ],
)
def test_main_lifts(movement, lift, variation):
    result = classify(movement)
    assert (result.lift, result.variation, result.is_main) == (lift, variation, True)


@pytest.mark.parametrize(
    "movement",
    [
        "Belt squat",
        "Hack Squat",
        "Pendulum Squats",
        "DB Split Squats",
        "Bulgarian split squat",
        "Belt Squat RDL",
        "Leg Press",
        "Incline DB press",
        "Machine Chest Press",
        "Lat Pulldowns",
        "Cable Rows",
    ],
)
def test_accessories_are_other(movement):
    result = classify(movement)
    assert (result.lift, result.variation, result.is_main) == ("other", "", False)
