"""Food search, the food diary, daily goals and saved meals."""

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from kiloplan.analytics.nutrition import Macros, for_grams
from kiloplan.storage.models import (
    DiaryEntry,
    Food,
    Lifter,
    NutritionGoal,
    SavedMeal,
    SavedMealItem,
    WaterDay,
)

MEALS = ("breakfast", "lunch", "dinner", "snacks")
DEFAULT_WATER_GOAL_ML = 2500.0


def macros_of(item: Food | DiaryEntry | SavedMealItem | NutritionGoal) -> Macros:
    return Macros(item.kcal, item.protein_g, item.carbs_g, item.fat_g)


def search_foods(session: Session, lifter: Lifter, query: str, limit: int = 25) -> list[Food]:
    """Foods whose name contains every word of the query: the lifter's own first, then shortest."""
    words = query.lower().split()
    if not words:
        return []
    statement = select(Food).where(
        or_(Food.source == "usda", Food.lifter_id == lifter.id),
        *(func.lower(Food.name).contains(word, autoescape=True) for word in words),
    )
    starts_with_query = func.lower(Food.name).startswith(words[0], autoescape=True)
    statement = statement.order_by(
        (Food.source == "custom").desc(),
        starts_with_query.desc(),
        func.length(Food.name),
        Food.name,
    )
    return list(session.scalars(statement.limit(limit)))


def create_custom_food(session: Session, lifter: Lifter, name: str, per_100g: Macros) -> Food:
    food = Food(
        source="custom",
        lifter_id=lifter.id,
        name=name.strip(),
        category="My foods",
        kcal=per_100g.kcal,
        protein_g=per_100g.protein_g,
        carbs_g=per_100g.carbs_g,
        fat_g=per_100g.fat_g,
    )
    session.add(food)
    session.flush()
    return food


def _check_meal(meal: str) -> None:
    if meal not in MEALS:
        raise ValueError(f"meal must be one of {', '.join(MEALS)}")


def log_food(
    session: Session, lifter: Lifter, day: date, meal: str, food: Food, grams: float
) -> DiaryEntry:
    """Log `grams` of a food. Its macros are worked out now and stored with the entry."""
    _check_meal(meal)
    if grams <= 0:
        raise ValueError("grams must be positive")
    eaten = for_grams(macros_of(food), grams)
    entry = DiaryEntry(
        lifter_id=lifter.id,
        day=day,
        meal=meal,
        food_id=food.id,
        description=food.name,
        grams=grams,
        kcal=eaten.kcal,
        protein_g=eaten.protein_g,
        carbs_g=eaten.carbs_g,
        fat_g=eaten.fat_g,
    )
    session.add(entry)
    session.flush()
    return entry


def quick_add(
    session: Session, lifter: Lifter, day: date, meal: str, description: str, macros: Macros
) -> DiaryEntry:
    """Log calories and macros directly, with no food behind them."""
    _check_meal(meal)
    entry = DiaryEntry(
        lifter_id=lifter.id,
        day=day,
        meal=meal,
        food_id=None,
        description=description.strip() or "Quick add",
        grams=None,
        kcal=macros.kcal,
        protein_g=macros.protein_g,
        carbs_g=macros.carbs_g,
        fat_g=macros.fat_g,
    )
    session.add(entry)
    session.flush()
    return entry


def entries_for_day(session: Session, lifter: Lifter, day: date) -> list[DiaryEntry]:
    statement = (
        select(DiaryEntry)
        .where(DiaryEntry.lifter_id == lifter.id, DiaryEntry.day == day)
        .order_by(DiaryEntry.id)
    )
    return list(session.scalars(statement))


def delete_entry(session: Session, lifter: Lifter, entry_id: int) -> bool:
    entry = session.get(DiaryEntry, entry_id)
    if entry is None or entry.lifter_id != lifter.id:
        return False
    session.delete(entry)
    return True


def get_goal(session: Session, lifter: Lifter) -> NutritionGoal | None:
    return session.get(NutritionGoal, lifter.id)


def set_goal(session: Session, lifter: Lifter, goal: Macros) -> NutritionGoal:
    stored = get_goal(session, lifter) or NutritionGoal(lifter_id=lifter.id)
    stored.kcal, stored.protein_g = goal.kcal, goal.protein_g
    stored.carbs_g, stored.fat_g = goal.carbs_g, goal.fat_g
    session.add(stored)
    session.flush()
    return stored


def saved_meals(session: Session, lifter: Lifter) -> list[SavedMeal]:
    statement = select(SavedMeal).where(SavedMeal.lifter_id == lifter.id).order_by(SavedMeal.name)
    return list(session.scalars(statement))


def save_meal_from_diary(
    session: Session, lifter: Lifter, name: str, day: date, meal: str
) -> SavedMeal:
    """Save what was logged for one meal of one day under a name."""
    _check_meal(meal)
    entries = [entry for entry in entries_for_day(session, lifter, day) if entry.meal == meal]
    if not entries:
        raise ValueError("there is nothing logged for that meal to save")
    saved = SavedMeal(lifter_id=lifter.id, name=name.strip())
    saved.items = [
        SavedMealItem(
            food_id=entry.food_id,
            description=entry.description,
            grams=entry.grams,
            kcal=entry.kcal,
            protein_g=entry.protein_g,
            carbs_g=entry.carbs_g,
            fat_g=entry.fat_g,
        )
        for entry in entries
    ]
    session.add(saved)
    session.flush()
    return saved


def log_saved_meal(
    session: Session, lifter: Lifter, meal_id: int, day: date, meal: str
) -> list[DiaryEntry] | None:
    """Add every item of a saved meal to the diary. None if the meal is not the lifter's."""
    _check_meal(meal)
    saved = session.get(SavedMeal, meal_id)
    if saved is None or saved.lifter_id != lifter.id:
        return None
    entries = [
        DiaryEntry(
            lifter_id=lifter.id,
            day=day,
            meal=meal,
            food_id=item.food_id,
            description=item.description,
            grams=item.grams,
            kcal=item.kcal,
            protein_g=item.protein_g,
            carbs_g=item.carbs_g,
            fat_g=item.fat_g,
        )
        for item in saved.items
    ]
    session.add_all(entries)
    session.flush()
    return entries


def delete_saved_meal(session: Session, lifter: Lifter, meal_id: int) -> bool:
    saved = session.get(SavedMeal, meal_id)
    if saved is None or saved.lifter_id != lifter.id:
        return False
    session.delete(saved)
    return True


def water_for_day(session: Session, lifter: Lifter, day: date) -> float:
    logged = session.get(WaterDay, (lifter.id, day))
    return logged.ml if logged else 0.0


def add_water(session: Session, lifter: Lifter, day: date, ml: float) -> float:
    """Add (or with a negative amount, take back) water for a day. Returns the new total."""
    logged = session.get(WaterDay, (lifter.id, day))
    if logged is None:
        logged = WaterDay(lifter_id=lifter.id, day=day, ml=0.0)
        session.add(logged)
    logged.ml = max(0.0, logged.ml + ml)
    session.flush()
    return logged.ml
