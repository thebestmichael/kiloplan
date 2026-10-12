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
