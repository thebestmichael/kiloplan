"""The assistant's tools that read the summary tables dbt builds."""

from datetime import date, timedelta

import duckdb
import pytest

from kiloplan.analytics.nutrition import Macros
from kiloplan.chatbot.assistant import Assistant
from kiloplan.chatbot.llm import ModelTurn, ScriptedModel, ToolCall
from kiloplan.chatbot.tools import ProgramTools
from kiloplan.storage import nutrition_store
from kiloplan.storage.program_store import get_or_create_lifter
from kiloplan.storage.warehouse import Warehouse

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)


@pytest.fixture
def lifter(session):
    lifter = get_or_create_lifter(session, "default")
    session.commit()
    return lifter


@pytest.fixture
def warehouse(tmp_path, lifter):
    """Hand-written summary tables, in the shape dbt produces."""
    path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "create table fct_weekly_volume (lifter_id integer, lift varchar, block_index integer, "
            "week_number integer, week_sequence integer, week_start date, total_sets integer, "
            "total_reps integer, volume_kg double, top_load_kg double)"
        )
        connection.executemany(
            "insert into fct_weekly_volume values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (lifter.id, "squat", 0, 3, 0, date(2026, 3, 16), 4, 18, 3000.0, 180.0),
                (lifter.id, "squat", 0, 4, 1, date(2026, 3, 23), 6, 28, 4500.0, 185.0),
                (lifter.id, "squat", 1, 1, 2, None, 1, 2, 300.0, 150.0),
                (lifter.id, "bench", 0, 4, 1, date(2026, 3, 23), 4, 20, 2000.0, 115.0),
                (lifter.id + 1, "squat", 0, 9, 9, None, 9, 99, 99999.0, 999.0),
            ],
        )
        connection.execute(
            "create table fct_daily_macros (lifter_id integer, diary_date date, kcal double, "
            "protein_g double, carbs_g double, fat_g double, entries integer)"
        )
        connection.executemany(
            "insert into fct_daily_macros values (?, ?, ?, ?, ?, ?, ?)",
            [
                (lifter.id, TODAY, 1800.0, 150.0, 190.0, 50.0, 6),
                (lifter.id, YESTERDAY, 2600.0, 190.0, 300.0, 70.0, 9),
                (lifter.id, TODAY - timedelta(days=20), 9999.0, 9.0, 9.0, 9.0, 1),
                (lifter.id + 1, TODAY, 5555.0, 5.0, 5.0, 5.0, 1),
            ],
        )
    return Warehouse(path)


@pytest.fixture
def tools(session, warehouse):
    return ProgramTools(session, "default", warehouse)


def test_weekly_volume_lists_recent_weeks_newest_first(tools):
    result = tools.weekly_volume("squat", weeks=2)
    assert result["status"] == "ok"
    assert [(week["block"], week["week"], week["week_of"]) for week in result["weeks"]] == [
        (2, 1, None),
        (1, 4, "2026-03-23"),
    ]
    week_4 = result["weeks"][1]
    assert (week_4["total_sets"], week_4["total_reps"]) == (6, 28)
    assert (week_4["volume_kg"], week_4["volume_lb"]) == (4500.0, 9920.8)
    assert (week_4["top_load_kg"], week_4["top_load_lb"]) == (185.0, 407.9)
    assert "block 1 week 4: 6 sets, 28 total reps, 9920.8 lb (4500.0 kg)" in result["text"]
    # the two weeks are added up by the tool: 300 + 4500 kg
    assert result["total_over_these_weeks"] == {
        "weeks": 2,
        "total_sets": 7,
        "total_reps": 30,
        "volume_kg": 4800.0,
        "volume_lb": 10582.2,
    }
    assert "Total over these 2 weeks: 10582.2 lb (4800.0 kg)." in result["text"]
    assert result["as_of"].endswith("UTC")


def test_weekly_volume_only_shows_the_lifters_own_weeks(tools):
    result = tools.weekly_volume("squat", weeks=12)
    assert len(result["weeks"]) == 3
    assert all(week["volume_kg"] < 99999 for week in result["weeks"])


def test_weekly_volume_with_nothing_to_show(tools):
    nothing = tools.weekly_volume("deadlift")
    assert (nothing["status"], nothing["kind"]) == ("no_match", "report")
    assert tools.weekly_volume("curls")["status"] == "invalid_input"


def test_daily_macros_for_today(tools):
    result = tools.daily_macros()
    assert result["status"] == "ok"
    assert result["days"] == [
        {
            "date": TODAY.isoformat(),
            "kcal": 1800.0,
            "protein_g": 150.0,
            "carbs_g": 190.0,
            "fat_g": 50.0,
        }
    ]
    assert result["average_per_logged_day"]["protein_g"] == 150.0
    assert "daily_goal" not in result


def test_daily_macros_over_several_days_with_the_average_and_goal(tools, session, lifter):
    nutrition_store.set_goal(session, lifter, Macros(2800, 200, 330, 75))
    session.commit()
    result = tools.daily_macros(days=7)
    assert [day["date"] for day in result["days"]] == [TODAY.isoformat(), YESTERDAY.isoformat()]
    assert (result["days_requested"], result["days_with_food_logged"]) == (7, 2)
    # the average is worked out here, not by the model: (1800 + 2600) / 2
    assert result["average_per_logged_day"] == {
        "kcal": 2200.0,
        "protein_g": 170.0,
        "carbs_g": 245.0,
        "fat_g": 60.0,
    }
    assert result["daily_goal"] == {
        "kcal": 2800.0,
        "protein_g": 200.0,
        "carbs_g": 330.0,
        "fat_g": 75.0,
    }
    assert result["note"].startswith("Only 2 of the last 7 days have food logged")


def test_reports_say_so_when_the_tables_have_not_been_built(session, tmp_path, lifter):
    for warehouse in (None, Warehouse(tmp_path / "missing.duckdb")):
        tools = ProgramTools(session, "default", warehouse)
        for result in (tools.weekly_volume("squat"), tools.daily_macros()):
            assert (result["status"], result["kind"]) == ("no_warehouse", "report")
            assert "kiloplan.pipeline" in result["message"]


def ask(tools, steps, question):
    model = ScriptedModel(list(steps))
    return Assistant(model, tools).ask(question)


def test_assistant_answers_a_protein_question_from_the_tables(tools):
    call = ModelTurn(tool_calls=(ToolCall("daily_macros", {"days": 1}),))
    answer = ask(
        tools, [call, ModelTurn(text="You have had 150 g of protein today.")], "Protein today?"
    )
    assert answer.status == "answered"
    assert answer.answer.startswith("You have had 150 g of protein today.")
    # the answer says how fresh the tables are
    assert "From your summary tables, last built" in answer.answer
    assert answer.basis_set is None


def test_assistant_cannot_invent_an_average(tools):
    call = ModelTurn(tool_calls=(ToolCall("daily_macros", {"days": 7}),))
    wrong = ModelTurn(text="You averaged about 2150 kcal.")
    answer = ask(tools, [call, wrong, wrong], "What have my calories averaged this week?")
    assert "2150" not in answer.answer
    assert "answer_corrected" in answer.flags
    # it falls back to what the tool returned
    assert answer.answer.startswith("Food logged, newest day first:")
    assert "1800 kcal" in answer.answer


def test_assistant_answers_a_volume_question(tools):
    call = ModelTurn(tool_calls=(ToolCall("weekly_volume", {"lift": "squat", "weeks": 2}),))
    answer = ask(tools, [call, ModelTurn(text="")], "How much squat volume lately?")
    assert answer.status == "answered"
    assert answer.answer.startswith("Squat volume, newest week first: block 2 week 1")


def test_assistant_explains_when_the_tables_are_missing(session, lifter):
    tools = ProgramTools(session, "default", None)
    call = ModelTurn(tool_calls=(ToolCall("daily_macros", {}),))
    answer = ask(tools, [call, ModelTurn(text="")], "Protein today?")
    assert answer.status == "needs_clarification"
    assert answer.flags == ["no_warehouse"]
    assert "have not been built yet" in answer.answer
    assert "Which set" not in answer.answer


def test_one_weeks_volume_cannot_be_passed_off_as_the_total(tools):
    call = ModelTurn(tool_calls=(ToolCall("weekly_volume", {"lift": "squat", "weeks": 2}),))
    wrong = ModelTurn(text="Over the last 2 weeks you did a total of 661.4 lb (300.0 kg).")
    right = ModelTurn(text="Over the last 2 weeks you did a total of 10582.2 lb (4800.0 kg).")
    model = ScriptedModel([call, wrong, right])
    answer = Assistant(model, tools).ask("How much squat volume over the last 2 weeks?")
    assert "Use that figure for any total" in model.seen[-1][-1]["content"]
    assert answer.answer.startswith("Over the last 2 weeks you did a total of 10582.2 lb")
    assert "answer_corrected" in answer.flags


def test_an_average_over_few_logged_days_says_so(tools):
    call = ModelTurn(tool_calls=(ToolCall("daily_macros", {"days": 7}),))
    text = ModelTurn(text="You averaged 2200 kcal a day.")
    answer = ask(tools, [call, text], "What have my calories averaged this week?")
    assert "Only 2 of the last 7 days have food logged" in answer.answer
