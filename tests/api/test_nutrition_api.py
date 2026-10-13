import pytest
from fastapi.testclient import TestClient

from kiloplan.api.main import app

client = TestClient(app)


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


def test_custom_foods_come_first_and_belong_to_their_lifter(foods, ben):
    mine = {"name": "Mum's chicken rice", "kcal": 150, "protein_g": 12, "carbs_g": 18, "fat_g": 3}
    created = client.post("/api/nutrition/foods", json=mine).json()
    assert (created["source"], created["category"]) == ("custom", "My foods")
    names = [
        food["name"] for food in client.get("/api/nutrition/foods", params={"q": "rice"}).json()
    ]
    assert names == ["Mum's chicken rice", "Rice, white, cooked"]

    other = ben.get("/api/nutrition/foods", params={"q": "rice"}).json()
    assert [food["name"] for food in other] == ["Rice, white, cooked"]
    log = {"day": "2026-10-13", "meal": "lunch", "food_id": created["id"], "grams": 100}
    assert ben.post("/api/nutrition/diary", json=log).status_code == 404


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


def test_diary_entries_can_be_deleted_only_by_their_lifter(foods, ben):
    entry = log(foods["Rice, white, cooked"], 100).json()
    path = f"/api/nutrition/diary/{entry['id']}"
    assert ben.delete(path).status_code == 404
    assert client.delete(path).status_code == 204
    assert client.delete(path).status_code == 404
    day = client.get("/api/nutrition/diary", params={"day": "2026-10-13"}).json()
    assert day["totals"]["kcal"] == 0


def test_diary_rejects_bad_input(foods):
    rice = foods["Rice, white, cooked"]
    assert log(rice, 0).status_code == 422
    assert log(rice, 100, meal="brunch").status_code == 422
    assert log(99999, 100).status_code == 404


def test_saved_meals(foods, ben):
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
    assert ben.post(f"{path}/log", json=target).status_code == 404
    assert ben.delete(path).status_code == 404
    assert ben.get("/api/nutrition/meals").json() == []
    assert client.delete(path).status_code == 204
    assert client.get("/api/nutrition/meals").json() == []


def test_water_is_tracked_per_day_and_never_goes_below_zero():
    day = {"day": "2026-10-13"}
    assert client.get("/api/nutrition/diary", params=day).json()["water_ml"] == 0
    assert client.post("/api/nutrition/water", json={**day, "ml": 250}).json() == {"water_ml": 250}
    assert client.post("/api/nutrition/water", json={**day, "ml": 500}).json() == {"water_ml": 750}
    assert client.post("/api/nutrition/water", json={**day, "ml": -250}).json() == {"water_ml": 500}

    logged = client.get("/api/nutrition/diary", params=day).json()
    assert logged["water_ml"] == 500
    assert client.get("/api/nutrition/diary", params={"day": "2026-10-14"}).json()["water_ml"] == 0

    assert client.post("/api/nutrition/water", json={**day, "ml": -900}).json() == {"water_ml": 0}


def test_water_has_no_upper_limit():
    request = {"day": "2026-10-13", "ml": 4500}
    assert client.post("/api/nutrition/water", json=request).json() == {"water_ml": 4500}
    assert client.post("/api/nutrition/water", json=request).json() == {"water_ml": 9000}


def test_recommended_water_appears_once_bodyweight_is_set(ben):
    day = {"day": "2026-10-13"}
    before = client.get("/api/nutrition/diary", params=day).json()
    assert (before["bodyweight_kg"], before["water_recommended_ml"]) == (None, None)

    saved = client.put("/api/nutrition/bodyweight", json={"bodyweight_kg": 90}).json()
    assert saved == {"bodyweight_kg": 90, "water_recommended_ml": 3150}
    after = client.get("/api/nutrition/diary", params=day).json()
    assert (after["bodyweight_kg"], after["water_recommended_ml"]) == (90, 3150)

    # changing it updates the recommendation, and it is kept per lifter
    client.put("/api/nutrition/bodyweight", json={"bodyweight_kg": 100})
    assert client.get("/api/nutrition/diary", params=day).json()["water_recommended_ml"] == 3500
    other = ben.get("/api/nutrition/diary", params=day).json()
    assert other["water_recommended_ml"] is None
    assert client.put("/api/nutrition/bodyweight", json={"bodyweight_kg": 0}).status_code == 422
