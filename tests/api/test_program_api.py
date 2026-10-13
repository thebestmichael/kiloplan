import pytest
from fastapi.testclient import TestClient

from kiloplan.api.main import app
from workbooks import as_bytes, line, program_workbook

client = TestClient(app)


def upload(workbook, browser=client):
    files = {"file": ("program.xlsx", as_bytes(workbook).getvalue())}
    return browser.post("/api/program/upload", files=files)


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


def test_programs_are_kept_per_account(ben):
    assert ben.get("/api/program").status_code == 404
    upload(small_program(top_set_load=298))
    upload(small_program(top_set_load=320), browser=ben)
    guest = client.get("/api/program").json()
    assert guest["rows"][0]["actual_load_kg"] == pytest.approx(298 * 0.45359237)
    assert ben.get("/api/program").json()["rows"][0]["actual_load_kg"] == pytest.approx(
        320 * 0.45359237
    )


def test_upload_rejects_non_workbook():
    files = {"file": ("notes.xlsx", b"this is not a spreadsheet")}
    response = client.post("/api/program/upload", files=files)
    assert response.status_code == 400
    assert "Excel workbook" in response.json()["detail"]


def test_upload_rejects_workbook_without_a_program():
    response = upload(program_workbook({"Reference": []}))
    assert response.status_code == 400
    assert "No program lines" in response.json()["detail"]
