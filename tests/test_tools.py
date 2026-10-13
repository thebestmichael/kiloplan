import pytest

from kiloplan.chatbot.tools import BELOW_CHART_NOTE, KG_PER_LB, TOOL_SCHEMAS, ProgramTools
from kiloplan.ingestion.coach_sheet import parse_workbook
from kiloplan.storage.program_store import store_program
from workbooks import EXAMPLE_PROGRAM, as_bytes, program_workbook


@pytest.fixture
def tools(session):
    result = parse_workbook(as_bytes(program_workbook(EXAMPLE_PROGRAM)))
    store_program(session, "ana", "program.xlsx", result)
    session.commit()
    return ProgramTools(session, "ana")


def test_find_sets_returns_the_set_the_lifter_describes(tools):
    result = tools.find_sets("squat", week_number=4, reps=3, stated_load=405, stated_rpe=9)
    assert result["status"] == "ok"
    found = result["set"]
    assert (found["movement"], found["block"], found["week"], found["day"]) == (
        "Squat",
        1,
        4,
        "Day 1",
    )
    assert (found["sets"], found["reps"], found["rpe"]) == (1, 3, "9")
    assert (found["load_lb"], found["load_kg"]) == (405.0, 183.7)
    assert (found["tab"], found["sheet_cell"], found["week_of"]) == ("Spring", "J5", "2026-03-23")
    assert "405.0 lb (183.7 kg), RPE 9" in found["description"]


def test_find_sets_accepts_a_load_in_kg(tools):
    result = tools.find_sets("squat", week_number=4, reps=3, stated_load=183.7, unit="kg")
    assert result["status"] == "ok"
    assert result["set"]["load_lb"] == 405.0


def test_find_sets_uses_the_most_recent_matching_week(tools):
    result = tools.find_sets("squat", reps=3)
    assert (result["status"], result["set"]["week"]) == ("ok", 4)
    assert result["older_weeks_also_matching"] == 1


def test_find_sets_reports_a_stated_load_that_disagrees_with_the_log(tools):
    result = tools.find_sets("squat", week_number=4, reps=3, stated_load=415, stated_rpe=9)
    assert result["status"] == "conflict"
    assert [logged["load_lb"] for logged in result["logged_sets"]] == [405.0]


def test_find_sets_reports_a_stated_rpe_that_disagrees_with_the_log(tools):
    result = tools.find_sets("squat", week_number=4, reps=3, stated_load=405, stated_rpe=8)
    assert result["status"] == "conflict"
    assert "RPE 8" in result["message"]
    assert [logged["rpe"] for logged in result["logged_sets"]] == ["9"]


def test_find_sets_is_ambiguous_when_different_sets_match(tools):
    result = tools.find_sets("squat", week_number=4, reps=5)
    assert result["status"] == "ambiguous"
    assert sorted(match["load_lb"] for match in result["matching_sets"]) == [365.0, 370.0, 380.0]


def test_find_sets_has_no_match_for_an_unlogged_week(tools):
    result = tools.find_sets("squat", week_number=2)
    assert result["status"] == "no_match"


def test_find_sets_does_not_swap_in_another_variation(tools):
    result = tools.find_sets("deadlift", variation="paused")
    assert result["status"] == "no_match"
    assert result["variations_with_data"] == ["competition"]

    paused = tools.find_sets("squat", variation="paused", week_number=4)
    assert (paused["status"], paused["set"]["movement"]) == ("ok", "Paused Squats")


def test_latest_top_set_is_the_heaviest_rpe_6_plus_set_of_the_latest_day(tools):
    # week 1 of the new block is newer but only logged as "<5", so week 4 day 3 is used
    result = tools.latest_top_set("squat")
    assert result["status"] == "ok"
    top = result["set"]
    assert (top["week"], top["day"], top["load_lb"], top["rpe"]) == (4, "Day 3", 380.0, "7")


def test_latest_top_set_needs_an_rpe_of_6_or_more(tools):
    result = tools.latest_top_set("bench")
    assert result["status"] == "no_match"
    assert (result["sets_logged_below_rpe_5"], result["sets_logged_at_rpe_5_to_6"]) == (1, 1)

    no_rpe = tools.latest_top_set("deadlift")
    assert (no_rpe["status"], no_rpe["sets_without_rpe"]) == ("no_match", 1)


def test_estimate_e1rm_from_a_logged_set(tools):
    found = tools.find_sets("squat", week_number=4, reps=3)["set"]
    result = tools.estimate_e1rm(set_id=found["set_id"])
    # 405 lb x 3 at RPE 9 = 4 theoretical reps: 405 * 36 / 33
    assert result["status"] == "ok"
    assert (result["e1rm_lb"], result["e1rm_kg"]) == (441.8, 200.4)
    assert result["based_on"] == {
        "load_kg": 183.7,
        "load_lb": 405.0,
        "reps": 3,
        "rpe": 9.0,
        "rpe_source": "logged",
        "reps_in_reserve": 1.0,
    }
    assert result["below_chart_range"] is False
    assert "note" not in result
    assert result["set"]["set_id"] == found["set_id"]


def test_estimate_e1rm_from_a_stated_set(tools):
    result = tools.estimate_e1rm(load=183.7, unit="kg", reps=3, rpe=9)
    assert (result["status"], result["e1rm_kg"]) == ("ok", 200.4)
    assert result["based_on"]["rpe_source"] == "stated"
    assert "set" not in result


def test_estimate_e1rm_flags_an_rpe_below_the_chart_range(tools):
    result = tools.estimate_e1rm(load=240, reps=5, rpe=5.5)
    assert result["below_chart_range"] is True
    assert result["note"] == BELOW_CHART_NOTE


def test_a_set_logged_below_rpe_5_cannot_be_a_basis(tools):
    logged = tools.find_sets("squat", week_number=1)["set"]
    assert logged["rpe"] == "<5"
    result = tools.estimate_e1rm(set_id=logged["set_id"])
    assert result["status"] == "cannot_calculate"
    assert "RPE is <5" in result["message"]
    assert tools.estimate_e1rm(set_id=logged["set_id"], rpe=7)["status"] == "conflict"


def test_a_set_with_no_logged_rpe_can_use_the_lifters_stated_rpe(tools):
    logged = tools.find_sets("deadlift", week_number=4)["set"]
    assert tools.estimate_e1rm(set_id=logged["set_id"])["status"] == "cannot_calculate"
    result = tools.estimate_e1rm(set_id=logged["set_id"], rpe=8)
    assert result["status"] == "ok"
    assert result["based_on"]["rpe_source"] == "stated by the lifter (not in the log)"


def test_target_load_for_the_example_question(tools):
    found = tools.find_sets("squat", week_number=4, reps=3, stated_load=405, stated_rpe=9)["set"]
    result = tools.target_load(target_reps=2, target_rpe=5, set_id=found["set_id"])
    # e1RM 441.8 lb; 2 reps at RPE 5 = 7 theoretical reps: 441.8 * 30 / 36
    assert result["status"] == "ok"
    assert (result["target_load_lb"], result["target_load_kg"]) == (368.2, 167.0)
    assert result["target_load_text"] == "368.2 lb (167.0 kg)"
    assert (result["e1rm_lb"], result["e1rm_text"]) == (441.8, "441.8 lb (200.4 kg)")
    assert result["target"] == {"reps": 2, "rpe": 5, "reps_in_reserve": 5}
    assert result["set"]["sheet_cell"] == "J5"
    # the target RPE is below the chart range even though the basis set is not
    assert result["below_chart_range"] is True
    assert result["note"] == BELOW_CHART_NOTE
    assert "_e1rm_kg_exact" not in result


def test_target_load_within_the_chart_range_has_no_note(tools):
    result = tools.target_load(target_reps=3, target_rpe=9, load=405, reps=3, rpe=9)
    assert result["target_load_lb"] == 405.0
    assert result["below_chart_range"] is False
    assert "note" not in result


def test_target_load_is_computed_at_full_precision(tools):
    result = tools.target_load(target_reps=2, target_rpe=5, load=405, reps=3, rpe=9)
    assert result["target_load_kg"] == pytest.approx(405 * KG_PER_LB * 36 / 33 * 30 / 36, abs=0.05)


def test_set_ids_from_another_lifter_are_not_found(tools, session):
    found = tools.find_sets("squat", week_number=4, reps=3)["set"]
    other = ProgramTools(session, "ben")
    assert other.find_sets("squat")["status"] == "no_program"
    assert other.estimate_e1rm(set_id=found["set_id"])["status"] == "no_match"


def test_call_dispatches_by_name_and_reports_bad_input(tools):
    ok = tools.call("latest_top_set", {"lift": "squat", "variation": None})
    assert ok["status"] == "ok"
    assert tools.call("delete_everything", {})["status"] == "invalid_input"
    assert tools.call("find_sets", {"lift": "curl"})["status"] == "invalid_input"
    assert tools.call("find_sets", {"lift": "squat", "colour": "red"})["status"] == "invalid_input"
    assert tools.call("estimate_e1rm", {"load": 100, "reps": 3})["status"] == "invalid_input"
    assert tools.call("estimate_e1rm", {"load": 100, "reps": 3, "rpe": 12})["status"] == (
        "invalid_input"
    )
    assert tools.call("estimate_e1rm", {"load": 100, "unit": "stone", "reps": 3, "rpe": 8})[
        "status"
    ] == ("invalid_input")


def test_every_schema_names_a_real_tool(tools):
    for schema in TOOL_SCHEMAS:
        assert callable(getattr(tools, schema["name"]))
        assert schema["parameters"]["type"] == "object"
