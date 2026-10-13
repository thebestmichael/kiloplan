import pytest
from fastapi.testclient import TestClient

from kiloplan.api.main import app
from workbooks import as_bytes, line, program_workbook

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


def upload(workbook, lifter=None):
    params = {"lifter": lifter} if lifter else {}
    files = {"file": ("program.xlsx", as_bytes(workbook).getvalue())}
    return client.post("/api/program/upload", files=files, params=params)


def small_program(top_set_load=298):
    return program_workbook(
        {
            "Block A": [
                ("Week 1", "7/13-19/26", {"Day 1": [line("Squats", 1, 7, top_set_load, "<5")]}),
                ("Week 2", "7/20-26/26", {"Day 1": [line("Paused Squats", 1, 7, 310, 11)]}),
            ],
            "Reference": [],
        }
    )


def test_upload_program_stores_and_returns_it():
    response = upload(small_program())
    assert response.status_code == 200
    body = response.json()
    assert body["lifter"] == "default"
    assert body["sheets"] == [
        {
            "name": "Block A",
            "blocks": 1,
            "weeks": 2,
            "lines": 2,
            "first_week": "2026-07-13",
            "last_week": "2026-07-20",
        }
    ]
    assert body["skipped_sheets"] == ["Reference"]
    assert [(issue["sheet"], issue["cell"]) for issue in body["issues"]] == [("Block A", "J5")]

    first, second = body["rows"]
    assert (first["movement"], first["lift"], first["variation"]) == (
        "Squats",
        "squat",
        "competition",
    )
    assert (first["block_index"], first["week_number"], first["week_start"]) == (0, 1, "2026-07-13")
    assert first["actual_load_kg"] == pytest.approx(298 * 0.45359237)
    assert (first["rpe"], first["rpe_below_5"]) == (None, True)
    assert (second["lift"], second["variation"], second["week_number"]) == ("squat", "paused", 2)


def test_get_program_returns_the_stored_upload():
    assert client.get("/api/program").status_code == 404
    uploaded = upload(small_program()).json()
    response = client.get("/api/program")
    assert response.status_code == 200
    assert response.json() == uploaded


def test_upload_replaces_the_lifters_previous_program():
    upload(small_program(top_set_load=298))
    upload(small_program(top_set_load=320))
    rows = client.get("/api/program").json()["rows"]
    assert len(rows) == 2
    assert rows[0]["actual_load_kg"] == pytest.approx(320 * 0.45359237)


def test_programs_are_kept_per_lifter():
    upload(small_program(top_set_load=298), lifter="ana")
    upload(small_program(top_set_load=320), lifter="ben")
    ana = client.get("/api/program", params={"lifter": "ana"}).json()
    assert ana["rows"][0]["actual_load_kg"] == pytest.approx(298 * 0.45359237)
    assert client.get("/api/program").status_code == 404


def test_upload_rejects_non_workbook():
    files = {"file": ("notes.xlsx", b"this is not a spreadsheet")}
    response = client.post("/api/program/upload", files=files)
    assert response.status_code == 400
    assert "Excel workbook" in response.json()["detail"]


def test_upload_rejects_workbook_without_a_program():
    response = upload(program_workbook({"Reference": []}))
    assert response.status_code == 400
    assert "No program lines" in response.json()["detail"]


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
