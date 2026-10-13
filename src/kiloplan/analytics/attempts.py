"""Meet attempt selection. All weights in kg."""

from kiloplan.analytics.e1rm import round_to_increment

# A common rule of thumb: open with something you could triple, take a second that
# sets up the third, and finish on the goal.
ATTEMPT_SHARES = (0.91, 0.96, 1.0)
MEET_INCREMENT_KG = 2.5


def select_attempts(
    goal_kg: float, increment_kg: float = MEET_INCREMENT_KG
) -> tuple[float, float, float]:
    """Opener, second and third attempt for a goal lift, on loadable meet weights."""
    if goal_kg <= 0:
        raise ValueError(f"goal_kg must be positive, got {goal_kg}")
    opener, second, third = (
        round_to_increment(goal_kg * share, increment_kg) for share in ATTEMPT_SHARES
    )
    return opener, second, third
