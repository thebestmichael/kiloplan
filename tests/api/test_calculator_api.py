import pytest
from fastapi.testclient import TestClient

from kiloplan.api.main import app

client = TestClient(app)


PAUSED_TRIPLE = {
    "pr_weight_kg": 180,
    "pr_reps": 3,
    "pr_rpe": 9,
    "target_reps": 3,
    "target_rpe": 5,
}


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_target_load_defaults_to_hybrid():
    response = client.post("/api/target-load", json=PAUSED_TRIPLE)
    assert response.status_code == 200
    body = response.json()
    assert body["e1rm_kg"] == pytest.approx(196.3636, abs=1e-4)
    assert body["target_weight_kg"] == pytest.approx(158.1818, abs=1e-4)


def test_target_load_with_epley():
    response = client.post("/api/target-load", json={**PAUSED_TRIPLE, "formula": "epley"})
    assert response.status_code == 200
    body = response.json()
    assert body["e1rm_kg"] == pytest.approx(204.0)
    assert body["target_weight_kg"] == pytest.approx(161.0526, abs=1e-4)


def test_target_load_with_brzycki():
    response = client.post("/api/target-load", json={**PAUSED_TRIPLE, "formula": "brzycki"})
    assert response.status_code == 200
    body = response.json()
    assert body["target_weight_kg"] == pytest.approx(158.1818, abs=1e-4)


@pytest.mark.parametrize(
    "override",
    [
        {"pr_weight_kg": 0},
        {"pr_reps": 0},
        {"pr_rpe": 10.5},
        {"target_rpe": 0},
        {"formula": "lombardi"},
    ],
)
def test_target_load_rejects_invalid_input(override):
    response = client.post("/api/target-load", json={**PAUSED_TRIPLE, **override})
    assert response.status_code == 422


def test_target_load_rejects_reps_beyond_brzycki_limit():
    response = client.post(
        "/api/target-load", json={**PAUSED_TRIPLE, "formula": "brzycki", "target_reps": 40}
    )
    assert response.status_code == 422
    assert "at most 36" in response.json()["detail"]


def test_rep_maxes():
    response = client.post("/api/rep-maxes", json={"weight_kg": 180, "reps": 3, "rpe": 9})
    assert response.status_code == 200
    body = response.json()
    assert body["e1rm_kg"] == pytest.approx(196.3636, abs=1e-4)
    assert [row["reps"] for row in body["rep_maxes"]] == list(range(1, 11))
    assert body["rep_maxes"][0]["weight_kg"] == pytest.approx(196.3636, abs=1e-4)
    assert [row["rpe"] for row in body["rpe_chart"]] == [10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5, 6]
    # the set it came from sits in the chart: 3 reps at RPE 9
    assert body["rpe_chart"][2]["weights_kg"][2] == pytest.approx(180)


def test_plates():
    stock = [{"weight": 25, "pairs": 8}, {"weight": 5, "pairs": 1}, {"weight": 1.25, "pairs": 1}]
    response = client.post("/api/plates", json={"target": 182.5, "bar": 20, "plates": stock})
    assert response.status_code == 200
    assert response.json() == {"per_side": [25, 25, 25, 5, 1.25], "total": 182.5, "shortfall": 0}

    below_bar = client.post("/api/plates", json={"target": 10, "bar": 20, "plates": stock})
    assert below_bar.status_code == 422
    assert "below the empty bar" in below_bar.json()["detail"]


def test_plates_total():
    request = {"per_side": [45, 45, 25], "bar": 45}
    assert client.post("/api/plates/total", json=request).json() == {"total": 275}


def test_points():
    request = {"sex": "male", "bodyweight_kg": 100, "total_kg": 1000}
    body = client.post("/api/points", json=request).json()
    assert body["wilks"] == pytest.approx(608.58907, abs=1e-4)
    assert body["wilks_2020"] == pytest.approx(729.4, abs=0.05)
    assert body["dots"] == pytest.approx(615.52, abs=0.01)
    assert body["ipf_gl"] > 0
    assert client.post("/api/points", json={**request, "sex": "other"}).status_code == 422


def test_attempts():
    body = client.post("/api/attempts", json={"squat_kg": 200, "deadlift_kg": 267.5}).json()
    assert body == {
        "attempts_kg": {"squat": [182.5, 192.5, 200.0], "deadlift": [242.5, 257.5, 267.5]},
        "total_kg": 467.5,
    }


def test_points_target():
    request = {"formula": "wilks", "sex": "male", "bodyweight_kg": 100, "target_points": 500}
    body = client.post("/api/points/target", json=request).json()
    assert body == {"total_kg": pytest.approx(821.57, abs=0.01)}

    too_light = {**request, "formula": "ipf_gl", "bodyweight_kg": 30}
    response = client.post("/api/points/target", json=too_light)
    assert response.status_code == 422
    assert "not defined" in response.json()["detail"]
    assert (
        client.post("/api/points/target", json={**request, "formula": "sinclair"}).status_code
        == 422
    )
