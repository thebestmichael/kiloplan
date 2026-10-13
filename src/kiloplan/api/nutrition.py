"""Food search, food diary, daily goals and saved meals."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kiloplan.analytics.nutrition import Macros, recommended_water_ml, remaining, total
from kiloplan.api.deps import DbSession, Owner
from kiloplan.storage import nutrition_store as store
from kiloplan.storage.models import DiaryEntry, Food, SavedMeal

router = APIRouter(prefix="/api/nutrition")

Meal = Literal["breakfast", "lunch", "dinner", "snacks"]


class MacrosModel(BaseModel):
    kcal: float = Field(ge=0, le=20000)
    protein_g: float = Field(ge=0, le=2000)
    carbs_g: float = Field(ge=0, le=2000)
    fat_g: float = Field(ge=0, le=2000)

    def to_macros(self) -> Macros:
        return Macros(self.kcal, self.protein_g, self.carbs_g, self.fat_g)


class SignedMacros(BaseModel):
    """Macros that may be negative, for what is left of a goal."""

    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


def _macros_out(macros: Macros) -> SignedMacros:
    return SignedMacros(
        kcal=macros.kcal, protein_g=macros.protein_g, carbs_g=macros.carbs_g, fat_g=macros.fat_g
    )


class PortionOut(BaseModel):
    description: str
    grams: float


class FoodOut(MacrosModel):
    """Macros are per 100 g."""

    id: int
    name: str
    category: str
    source: str
    portions: list[PortionOut]


def _food_out(food: Food) -> FoodOut:
    return FoodOut(
        id=food.id,
        name=food.name,
        category=food.category,
        source=food.source,
        kcal=food.kcal,
        protein_g=food.protein_g,
        carbs_g=food.carbs_g,
        fat_g=food.fat_g,
        portions=[PortionOut(description=p.description, grams=p.grams) for p in food.portions],
    )


@router.get("/foods")
def search_foods(session: DbSession, q: str, owner: Owner) -> list[FoodOut]:
    foods = store.search_foods(session, owner, q)
    session.commit()
    return [_food_out(food) for food in foods]


class CustomFoodRequest(MacrosModel):
    """A lifter's own food, with macros per 100 g."""

    name: str = Field(min_length=1, max_length=200)


@router.post("/foods")
def create_food(request: CustomFoodRequest, session: DbSession, owner: Owner) -> FoodOut:
    food = store.create_custom_food(session, owner, request.name, request.to_macros())
    session.commit()
    return _food_out(food)


class EntryOut(SignedMacros):
    id: int
    description: str
    grams: float | None


class MealOut(BaseModel):
    meal: str
    entries: list[EntryOut]
    totals: SignedMacros


class DayOut(BaseModel):
    day: date
    meals: list[MealOut]
    totals: SignedMacros
    goal: SignedMacros | None
    remaining: SignedMacros | None
    water_ml: float
    bodyweight_kg: float | None
    water_recommended_ml: float | None


def _entry_out(entry: DiaryEntry) -> EntryOut:
    return EntryOut(
        id=entry.id,
        description=entry.description,
        grams=entry.grams,
        kcal=entry.kcal,
        protein_g=entry.protein_g,
        carbs_g=entry.carbs_g,
        fat_g=entry.fat_g,
    )


@router.get("/diary")
def get_day(session: DbSession, day: date, owner: Owner) -> DayOut:
    """One day of the food diary by meal, with totals and what is left of the goal."""
    entries = store.entries_for_day(session, owner, day)
    goal = store.get_goal(session, owner)
    water_ml = store.water_for_day(session, owner, day)
    bodyweight_kg = store.get_bodyweight_kg(session, owner)
    session.commit()
    eaten = total(store.macros_of(entry) for entry in entries)
    meals = []
    for meal in store.MEALS:
        in_meal = [entry for entry in entries if entry.meal == meal]
        meals.append(
            MealOut(
                meal=meal,
                entries=[_entry_out(entry) for entry in in_meal],
                totals=_macros_out(total(store.macros_of(entry) for entry in in_meal)),
            )
        )
    goal_macros = store.macros_of(goal) if goal else None
    return DayOut(
        day=day,
        meals=meals,
        totals=_macros_out(eaten),
        goal=_macros_out(goal_macros) if goal_macros else None,
        remaining=_macros_out(remaining(goal_macros, eaten)) if goal_macros else None,
        water_ml=water_ml,
        bodyweight_kg=bodyweight_kg,
        water_recommended_ml=recommended_water_ml(bodyweight_kg) if bodyweight_kg else None,
    )


class LogFoodRequest(BaseModel):
    day: date
    meal: Meal
    food_id: int
    grams: float = Field(gt=0, le=10000)


@router.post("/diary")
def log_food(request: LogFoodRequest, session: DbSession, owner: Owner) -> EntryOut:
    food = session.get(Food, request.food_id)
    if food is None or (food.source == "custom" and food.lifter_id != owner.id):
        raise HTTPException(status_code=404, detail="No such food.")
    entry = store.log_food(session, owner, request.day, request.meal, food, request.grams)
    session.commit()
    return _entry_out(entry)


class QuickAddRequest(MacrosModel):
    day: date
    meal: Meal
    description: str = Field(default="", max_length=200)


@router.post("/diary/quick-add")
def quick_add(request: QuickAddRequest, session: DbSession, owner: Owner) -> EntryOut:
    entry = store.quick_add(
        session, owner, request.day, request.meal, request.description, request.to_macros()
    )
    session.commit()
    return _entry_out(entry)


@router.delete("/diary/{entry_id}", status_code=204)
def delete_entry(entry_id: int, session: DbSession, owner: Owner) -> None:
    if not store.delete_entry(session, owner, entry_id):
        raise HTTPException(status_code=404, detail="No such diary entry.")
    session.commit()


class WaterRequest(BaseModel):
    """`ml` is added to the day's total; a negative amount takes water back."""

    day: date
    ml: float = Field(ge=-5000, le=5000)


@router.post("/water")
def add_water(request: WaterRequest, session: DbSession, owner: Owner) -> dict[str, float]:
    water_ml = store.add_water(session, owner, request.day, request.ml)
    session.commit()
    return {"water_ml": water_ml}


class BodyweightRequest(BaseModel):
    bodyweight_kg: float = Field(gt=0, le=400)


@router.put("/bodyweight")
def set_bodyweight(
    request: BodyweightRequest, session: DbSession, owner: Owner
) -> dict[str, float]:
    """Store the lifter's bodyweight, which sets their recommended water intake."""
    store.set_bodyweight_kg(session, owner, request.bodyweight_kg)
    session.commit()
    return {
        "bodyweight_kg": request.bodyweight_kg,
        "water_recommended_ml": recommended_water_ml(request.bodyweight_kg),
    }


@router.put("/goal")
def set_goal(request: MacrosModel, session: DbSession, owner: Owner) -> SignedMacros:
    goal = store.set_goal(session, owner, request.to_macros())
    session.commit()
    return _macros_out(store.macros_of(goal))


class SavedMealItemOut(SignedMacros):
    description: str
    grams: float | None


class SavedMealOut(BaseModel):
    id: int
    name: str
    items: list[SavedMealItemOut]
    totals: SignedMacros


def _meal_out(meal: SavedMeal) -> SavedMealOut:
    return SavedMealOut(
        id=meal.id,
        name=meal.name,
        items=[
            SavedMealItemOut(
                description=item.description,
                grams=item.grams,
                kcal=item.kcal,
                protein_g=item.protein_g,
                carbs_g=item.carbs_g,
                fat_g=item.fat_g,
            )
            for item in meal.items
        ],
        totals=_macros_out(total(store.macros_of(item) for item in meal.items)),
    )


@router.get("/meals")
def list_meals(session: DbSession, owner: Owner) -> list[SavedMealOut]:
    meals = store.saved_meals(session, owner)
    session.commit()
    return [_meal_out(meal) for meal in meals]


class SaveMealRequest(BaseModel):
    """Saves what is logged for one meal of one day."""

    name: str = Field(min_length=1, max_length=100)
    day: date
    meal: Meal


@router.post("/meals")
def save_meal(request: SaveMealRequest, session: DbSession, owner: Owner) -> SavedMealOut:
    try:
        saved = store.save_meal_from_diary(session, owner, request.name, request.day, request.meal)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    session.commit()
    return _meal_out(saved)


class LogMealRequest(BaseModel):
    day: date
    meal: Meal


@router.post("/meals/{meal_id}/log")
def log_meal(
    meal_id: int, request: LogMealRequest, session: DbSession, owner: Owner
) -> list[EntryOut]:
    entries = store.log_saved_meal(session, owner, meal_id, request.day, request.meal)
    if entries is None:
        raise HTTPException(status_code=404, detail="No such saved meal.")
    session.commit()
    return [_entry_out(entry) for entry in entries]


@router.delete("/meals/{meal_id}", status_code=204)
def delete_meal(meal_id: int, session: DbSession, owner: Owner) -> None:
    if not store.delete_saved_meal(session, owner, meal_id):
        raise HTTPException(status_code=404, detail="No such saved meal.")
    session.commit()
