import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from kiloplan.analytics.nutrition import Macros, for_grams, kcal_from_macros, remaining, total
from kiloplan.api.main import app
from kiloplan.ingestion.usda import load_foods, read_foods
from kiloplan.storage.models import Food

client = TestClient(app)

FOOD_CSV = """fdc_id,data_type,description,food_category_id,publication_date
1,sr_legacy_food,"Chicken, breast, cooked",5,2019-04-01
2,sr_legacy_food,"Rice, white, cooked",20,2019-04-01
3,sr_legacy_food,Mystery powder,99,2019-04-01
"""
NUTRIENT_CSV = """id,fdc_id,nutrient_id,amount
1,1,1008,165
2,1,1003,31
3,1,1004,3.6
4,1,1005,0
5,2,1008,130
6,2,1003,2.7
7,2,1004,0.3
8,2,1005,28.2
9,2,1079,0.4
10,2,1093,1
11,3,1003,80
12,3,1005,5
13,3,1004,4
"""
PORTION_CSV = """id,fdc_id,seq_num,amount,measure_unit_id,portion_description,modifier,gram_weight
1,2,2,1,9999,,"cup, packed",186
2,2,1,1,9999,,cup,158
3,1,1,1,9999,,breast,0
"""
CATEGORY_CSV = """id,code,description
5,0500,Poultry Products
20,2000,Cereal Grains and Pasta
"""


@pytest.fixture
def usda_zip(tmp_path):
    path = tmp_path / "foods.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in (
            ("food.csv", FOOD_CSV),
            ("food_nutrient.csv", NUTRIENT_CSV),
            ("food_portion.csv", PORTION_CSV),
            ("food_category.csv", CATEGORY_CSV),
        ):
            archive.writestr(f"dataset/{name}", content)
    return path


@pytest.fixture
def foods(usda_zip, session):
    load_foods(session, read_foods(usda_zip))
    session.commit()
    return {food.name: food.id for food in session.scalars(select(Food))}


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


def test_read_foods(usda_zip):
    chicken, rice, powder = read_foods(usda_zip)
    assert (chicken.fdc_id, chicken.name, chicken.category) == (
        1,
        "Chicken, breast, cooked",
        "Poultry Products",
    )
    assert chicken.kcal == 165
    # a portion with no gram weight is dropped
    assert chicken.portions == []
    # portions come back in the dataset's order, and other nutrients are ignored
    assert rice.portions == [("1 cup", 158.0), ("1 cup, packed", 186.0)]
    assert rice.nutrients == {1008: 130.0, 1003: 2.7, 1004: 0.3, 1005: 28.2, 1079: 0.4}
    # no energy value: 4 * 80 + 4 * 5 + 9 * 4
    assert (powder.category, powder.kcal) == ("", 376)


def test_load_foods_updates_rather_than_duplicates(usda_zip, session):
    records = read_foods(usda_zip)
    assert load_foods(session, records) == 3
    records[1].nutrients[1008] = 131
    load_foods(session, records)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Food)) == 3
    rice = session.scalar(select(Food).where(Food.fdc_id == 2))
    assert (rice.kcal, rice.fiber_g, len(rice.portions)) == (131, 0.4, 2)


def test_food_search_matches_every_word(foods):
    names = [
        food["name"] for food in client.get("/api/nutrition/foods", params={"q": "RICE"}).json()
    ]
    assert names == ["Rice, white, cooked"]
    found = client.get("/api/nutrition/foods", params={"q": "cooked chicken"}).json()
    assert [food["name"] for food in found] == ["Chicken, breast, cooked"]
    assert (found[0]["kcal"], found[0]["protein_g"], found[0]["source"]) == (165, 31, "usda")
    assert client.get("/api/nutrition/foods", params={"q": "tofu"}).json() == []
    assert client.get("/api/nutrition/foods", params={"q": "  "}).json() == []


def test_custom_foods_come_first_and_belong_to_their_lifter(foods):
    mine = {"name": "Mum's chicken rice", "kcal": 150, "protein_g": 12, "carbs_g": 18, "fat_g": 3}
    created = client.post("/api/nutrition/foods", json=mine).json()
    assert (created["source"], created["category"]) == ("custom", "My foods")
    names = [
        food["name"] for food in client.get("/api/nutrition/foods", params={"q": "rice"}).json()
    ]
    assert names == ["Mum's chicken rice", "Rice, white, cooked"]

    other = client.get("/api/nutrition/foods", params={"q": "rice", "lifter": "ben"}).json()
    assert [food["name"] for food in other] == ["Rice, white, cooked"]
    log = {"day": "2026-10-13", "meal": "lunch", "food_id": created["id"], "grams": 100}
    assert client.post("/api/nutrition/diary", json={**log, "lifter": "ben"}).status_code == 404


def log(food_id, grams, meal="lunch", day="2026-10-13"):
    request = {"day": day, "meal": meal, "food_id": food_id, "grams": grams}
    return client.post("/api/nutrition/diary", json=request)


def test_diary_day_with_totals_goal_and_remaining(foods):
    chicken = log(foods["Chicken, breast, cooked"], 150).json()
    assert (chicken["description"], chicken["grams"]) == ("Chicken, breast, cooked", 150)
    assert (chicken["kcal"], chicken["protein_g"]) == (247.5, 46.5)
    log(foods["Rice, white, cooked"], 200)
    quick = {"day": "2026-10-13", "meal": "snacks", "description": "Protein bar"}
    quick |= {"kcal": 200, "protein_g": 20, "carbs_g": 22, "fat_g": 7}
    assert client.post("/api/nutrition/diary/quick-add", json=quick).json()["grams"] is None
    log(foods["Rice, white, cooked"], 100, day="2026-10-14")

    day = client.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()
    assert [meal["meal"] for meal in day["meals"]] == ["breakfast", "lunch", "dinner", "snacks"]
    lunch, snacks = day["meals"][1], day["meals"][3]
    assert [entry["description"] for entry in lunch["entries"]] == [
        "Chicken, breast, cooked",
        "Rice, white, cooked",
    ]
    assert lunch["totals"]["kcal"] == pytest.approx(507.5)
    assert snacks["entries"][0]["description"] == "Protein bar"
    assert day["totals"] == {
        "kcal": pytest.approx(707.5),
        "protein_g": pytest.approx(71.9),
        "carbs_g": pytest.approx(78.4),
        "fat_g": pytest.approx(13.0),
    }
    assert (day["goal"], day["remaining"]) == (None, None)

    goal = {"kcal": 2800, "protein_g": 200, "carbs_g": 330, "fat_g": 75}
    assert client.put("/api/nutrition/goal", json=goal).json() == goal
    day = client.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()
    assert day["goal"] == goal
    assert day["remaining"]["kcal"] == pytest.approx(2092.5)
    assert day["remaining"]["protein_g"] == pytest.approx(128.1)

    # setting the goal again replaces it
    client.put("/api/nutrition/goal", json={**goal, "kcal": 500})
    day = client.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()
    assert day["remaining"]["kcal"] == pytest.approx(-207.5)


def test_diary_entries_can_be_deleted_only_by_their_lifter(foods):
    entry = log(foods["Rice, white, cooked"], 100).json()
    path = f"/api/nutrition/diary/{entry['id']}"
    assert client.delete(path, params={"lifter": "ben"}).status_code == 404
    assert client.delete(path).status_code == 204
    assert client.delete(path).status_code == 404
    day = client.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()
    assert day["totals"]["kcal"] == 0


def test_diary_rejects_bad_input(foods):
    rice = foods["Rice, white, cooked"]
    assert log(rice, 0).status_code == 422
    assert log(rice, 100, meal="brunch").status_code == 422
    assert log(99999, 100).status_code == 404


def test_saved_meals(foods):
    log(foods["Chicken, breast, cooked"], 150)
    log(foods["Rice, white, cooked"], 200)
    save = {"name": "Chicken and rice", "day": "2026-10-13", "meal": "lunch"}
    saved = client.post("/api/nutrition/meals", json=save).json()
    assert saved["name"] == "Chicken and rice"
    assert [(item["description"], item["grams"]) for item in saved["items"]] == [
        ("Chicken, breast, cooked", 150),
        ("Rice, white, cooked", 200),
    ]
    assert saved["totals"]["kcal"] == pytest.approx(507.5)
    assert [meal["id"] for meal in client.get("/api/nutrition/meals").json()] == [saved["id"]]

    # logging it on another day adds every item to that meal
    target = {"day": "2026-10-14", "meal": "dinner"}
    logged = client.post(f"/api/nutrition/meals/{saved['id']}/log", json=target).json()
    assert len(logged) == 2
    dinner = client.get("/api/nutrition/diary", params={"day": "2026-10-14"}).json()["meals"][2]
    assert dinner["totals"]["kcal"] == pytest.approx(507.5)

    nothing = {"name": "Empty", "day": "2026-10-13", "meal": "breakfast"}
    assert client.post("/api/nutrition/meals", json=nothing).status_code == 422
    path = f"/api/nutrition/meals/{saved['id']}"
    assert client.post(f"{path}/log", json={**target, "lifter": "ben"}).status_code == 404
    assert client.delete(path, params={"lifter": "ben"}).status_code == 404
    assert client.delete(path).status_code == 204
    assert client.get("/api/nutrition/meals").json() == []
