"""Maps a free-text movement name to a lift and a variation."""

from dataclasses import dataclass

OTHER = "other"
COMPETITION = "competition"

LIFT_WORDS = {
    "squat": "squat",
    "squats": "squat",
    "bench": "bench",
    "deadlift": "deadlift",
    "deadlifts": "deadlift",
}
# bench variations that are written without the word "bench"
BENCH_PRESS_WORDS = {"spoto", "spotto", "larsen"}
# movements that mention a main lift but are accessories
ACCESSORY_WORDS = {
    "belt",
    "hack",
    "pendulum",
    "split",
    "bulgarian",
    "db",
    "rdl",
    "crossack",
    "cossack",
    "machine",
}
DROPPED_WORDS = {"comp", "competition", "press"}
WORD_SPELLINGS = {"pause": "paused", "pauses": "paused", "spotto": "spoto"}


@dataclass(frozen=True)
class Lift:
    lift: str
    variation: str

    @property
    def is_main(self) -> bool:
        return self.lift != OTHER


def classify(movement: str) -> Lift:
    """`Paused Squats` -> squat/paused, `Comp Bench` -> bench/competition, `Leg Press` -> other."""
    words = movement.lower().split()
    if ACCESSORY_WORDS.intersection(words):
        return Lift(OTHER, "")
    lift = next((LIFT_WORDS[word] for word in words if word in LIFT_WORDS), None)
    if lift is None and BENCH_PRESS_WORDS.intersection(words) and "press" in words:
        lift = "bench"
    if lift is None:
        return Lift(OTHER, "")
    kept = [
        WORD_SPELLINGS.get(word, word)
        for word in words
        if word not in LIFT_WORDS and word not in DROPPED_WORDS
    ]
    return Lift(lift, " ".join(kept) or COMPETITION)
