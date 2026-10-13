import json
import os

import pytest
from fastapi.testclient import TestClient

from kiloplan.api.main import app, get_chat_model
from kiloplan.chatbot.assistant import (
    NO_ANSWER,
    NOT_CHECKED_NOTE,
    PAIN_REFERRAL,
    Assistant,
    mentions_pain,
    numbers_in,
    unsupported_numbers,
)
from kiloplan.chatbot.llm import (
    ModelTurn,
    ModelUnavailableError,
    OllamaModel,
    ScriptedModel,
    ToolCall,
)
from kiloplan.chatbot.tools import BELOW_CHART_NOTE, ProgramTools
from kiloplan.ingestion.coach_sheet import parse_workbook
from kiloplan.storage.program_store import store_program
from workbooks import EXAMPLE_PROGRAM, as_bytes, program_workbook

EXAMPLE_QUESTION = (
    "I took 405 for 3 reps on squat in week 4 at RPE 9. Now I'm on week 1 of a new block "
    "and have squat for 2 reps at RPE 5. What weight should I take?"
)
FIND_THE_SET = ModelTurn(
    tool_calls=(
        ToolCall(
            "find_sets",
            {
                "lift": "squat",
                "week_number": 4,
                "reps": 3,
                "stated_load": 405,
                "stated_rpe": 9,
                "unit": "lb",
            },
        ),
    )
)
GOOD_ANSWER = (
    "Take 368.2 lb for your 2 reps at RPE 5. Your week 4 set of 405 for 3 at RPE 9 gives "
    "an estimated 1RM of 441.8 lb."
)


def target_from_found_set(messages):
    """Calls target_load with the set_id the lookup returned, as a real model would."""
    found = json.loads(messages[-1]["content"])
    arguments = {"set_id": found["set"]["set_id"], "target_reps": 2, "target_rpe": 5}
    return ModelTurn(tool_calls=(ToolCall("target_load", arguments),))


def say(text):
    return ModelTurn(text=text)


@pytest.fixture
def tools(session):
    result = parse_workbook(as_bytes(program_workbook(EXAMPLE_PROGRAM)))
    store_program(session, "default", "program.xlsx", result)
    session.commit()
    return ProgramTools(session, "default")


def ask(tools, steps, question=EXAMPLE_QUESTION):
    model = ScriptedModel(list(steps))
    return Assistant(model, tools).ask(question), model


def test_example_question_end_to_end(tools):
    answer, model = ask(tools, [FIND_THE_SET, target_from_found_set, say(GOOD_ANSWER)])

    assert answer.status == "answered"
    assert [calc.tool for calc in answer.calculations] == ["find_sets", "target_load"]
    assert model.steps == []

    # 1. the logged set was looked up, and is shown as the basis
    basis = answer.basis_set
    assert (basis["movement"], basis["block"], basis["week"], basis["day"]) == (
        "Squat",
        1,
        4,
        "Day 1",
    )
    assert (basis["load_lb"], basis["reps"], basis["rpe"], basis["sheet_cell"]) == (
        405.0,
        3,
        "9",
        "J5",
    )
    assert f"Based on: {basis['description']}." in answer.answer

    # 2 and 3. e1RM and target load come from the calculator: 405 * 36/33, then * 30/36
    calculation = answer.calculations[1].result
    assert (calculation["e1rm_lb"], calculation["target_load_lb"]) == (441.8, 368.2)
    assert "368.2 lb" in answer.answer
    assert "441.8 lb" in answer.answer

    # 4. the below-chart rule was used for RPE 5, and the answer says so
    assert answer.flags == ["below_chart_range"]
    assert BELOW_CHART_NOTE in answer.answer

    # every number in the answer traces to the question or a tool result
    assert unsupported_numbers(answer.answer, EXAMPLE_QUESTION, answer.calculations) == set()


def test_example_question_through_the_api(tools):
    model = ScriptedModel([FIND_THE_SET, target_from_found_set, say(GOOD_ANSWER)])
    app.dependency_overrides[get_chat_model] = lambda: model
    response = TestClient(app).post("/api/assistant/ask", json={"question": EXAMPLE_QUESTION})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["basis_set"]["sheet_cell"] == "J5"
    assert body["calculations"][1]["result"]["target_load_text"] == "368.2 lb (167.0 kg)"
    assert body["flags"] == ["below_chart_range"]


def test_the_model_sees_tool_results_before_answering(tools):
    _, model = ask(tools, [FIND_THE_SET, target_from_found_set, say(GOOD_ANSWER)])
    final_request = model.seen[-1]
    assert [message["role"] for message in final_request] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
    ]
    assert json.loads(final_request[-1]["content"])["target_load_lb"] == 368.2


def test_an_invented_number_is_sent_back_for_a_rewrite(tools):
    answer, model = ask(
        tools,
        [FIND_THE_SET, target_from_found_set, say("Take about 370 lb."), say(GOOD_ANSWER)],
    )
    assert answer.status == "answered"
    assert "370" not in answer.answer
    assert "368.2 lb" in answer.answer
    assert "answer_corrected" in answer.flags
    assert "370" in model.seen[-1][-1]["content"]


def test_an_answer_that_stays_wrong_is_replaced_from_the_tool_results(tools):
    answer, _ = ask(
        tools,
        [FIND_THE_SET, target_from_found_set, say("Take about 370 lb."), say("Fine: 365 lb.")],
    )
    assert answer.status == "answered"
    assert answer.answer.startswith(
        "Take 368.2 lb (167.0 kg) for 2 reps at RPE 5. That uses an estimated 1RM of "
        "441.8 lb (200.4 kg)."
    )
    assert "370" not in answer.answer
    assert "365" not in numbers_in(answer.answer.split("Based on")[0])
    assert BELOW_CHART_NOTE in answer.answer


def test_no_matching_set_gets_a_question_not_a_load(tools):
    lookup = ModelTurn(tool_calls=(ToolCall("find_sets", {"lift": "squat", "week_number": 2}),))
    answer, _ = ask(tools, [lookup, say("I could not find a week 2 squat. Which set do you mean?")])
    assert answer.status == "needs_clarification"
    assert answer.flags == ["no_match"]
    assert answer.basis_set is None
    assert answer.answer == "I could not find a week 2 squat. Which set do you mean?"


def test_a_stated_rpe_that_disagrees_with_the_log_is_reported(tools):
    question = EXAMPLE_QUESTION.replace("at RPE 9", "at RPE 8")
    lookup = ModelTurn(
        tool_calls=(
            ToolCall(
                "find_sets",
                {"lift": "squat", "week_number": 4, "reps": 3, "stated_load": 405, "stated_rpe": 8},
            ),
        )
    )
    # the model pushes on with the lifter's numbers and offers a load anyway
    stated = {
        "stated_load": 405,
        "stated_reps": 3,
        "stated_rpe": 8,
        "target_reps": 2,
        "target_rpe": 5,
    }
    calculate = ModelTurn(tool_calls=(ToolCall("target_load", stated),))
    answer, _ = ask(tools, [lookup, calculate, say("Take 356.9 lb.")], question)

    assert answer.status == "needs_clarification"
    assert answer.flags == ["conflict"]
    assert "356.9" not in answer.answer
    assert "RPE 8, but the log shows a different RPE" in answer.answer
    assert "Squat 1x3 at 405.0 lb (183.7 kg), RPE 9" in answer.answer
    assert answer.answer.endswith("Which set should I use?")


def test_several_matching_sets_are_listed_for_the_lifter_to_choose(tools):
    lookup = ModelTurn(
        tool_calls=(ToolCall("find_sets", {"lift": "squat", "week_number": 4, "reps": 5}),)
    )
    answer, _ = ask(tools, [lookup, say("")], "What was my squat for 5 in week 4?")
    assert answer.status == "needs_clarification"
    assert answer.flags == ["ambiguous"]
    for load in ("365.0 lb", "370.0 lb", "380.0 lb"):
        assert load in answer.answer


def test_a_set_logged_below_rpe_5_is_not_used_as_a_basis(tools):
    lookup = ModelTurn(tool_calls=(ToolCall("find_sets", {"lift": "squat", "week_number": 1}),))

    def calculate(messages):
        found = json.loads(messages[-1]["content"])
        arguments = {"set_id": found["set"]["set_id"], "target_reps": 2, "target_rpe": 7}
        return ModelTurn(tool_calls=(ToolCall("target_load", arguments),))

    answer, _ = ask(tools, [lookup, calculate, say("")], "What should I take for 2 at RPE 7?")
    assert answer.status == "needs_clarification"
    assert answer.flags == ["cannot_calculate"]
    assert "RPE is <5" in answer.answer


def test_pain_gets_a_referral_and_no_tools_or_model(tools):
    question = "My knee hurts on squats. I did 405 for 3 at RPE 9, what should I take for 2?"
    answer, model = ask(tools, [], question)
    assert answer.status == "referred"
    assert answer.answer == PAIN_REFERRAL
    assert answer.calculations == []
    assert answer.flags == ["pain_or_injury"]
    assert model.seen == []


@pytest.mark.parametrize(
    "text",
    [
        "sharp pain in my lower back",
        "I tweaked my shoulder benching",
        "my elbow is aching",
        "think I strained a hamstring",
        "is it ok to train with an injury?",
    ],
)
def test_mentions_pain(text):
    assert mentions_pain(text)


@pytest.mark.parametrize(
    "text",
    [EXAMPLE_QUESTION, "What is my best paused squat?", "I pulled 500 for 2 last week, what next?"],
)
def test_ordinary_questions_do_not_mention_pain(text):
    assert not mentions_pain(text)


def test_an_answer_with_numbers_but_no_tool_calls_is_not_passed_on(tools):
    answer, _ = ask(tools, [say("Take 365 lb."), say("Take 365 lb.")])
    assert answer.status == "needs_clarification"
    assert answer.answer == NO_ANSWER
    assert "no_tool_result" in answer.flags


def test_a_calculation_from_stated_numbers_says_it_was_not_checked(tools):
    stated = {
        "stated_load": 405,
        "unit": "lb",
        "stated_reps": 3,
        "stated_rpe": 9,
        "target_reps": 2,
        "target_rpe": 7,
    }
    calculate = ModelTurn(tool_calls=(ToolCall("target_load", stated),))
    answer, _ = ask(tools, [calculate, say("Take 392.7 lb.")])
    assert answer.status == "answered"
    assert answer.basis_set is None
    assert answer.flags == ["not_checked_against_log"]
    assert NOT_CHECKED_NOTE in answer.answer


def test_latest_top_set_is_used_when_no_set_is_named(tools):
    lookup = ModelTurn(tool_calls=(ToolCall("latest_top_set", {"lift": "squat"}),))

    def calculate(messages):
        found = json.loads(messages[-1]["content"])
        arguments = {"set_id": found["set"]["set_id"], "target_reps": 3, "target_rpe": 8}
        return ModelTurn(tool_calls=(ToolCall("target_load", arguments),))

    answer, _ = ask(tools, [lookup, calculate, say("")], "What should I squat for 3 at RPE 8?")
    assert answer.status == "answered"
    assert (answer.basis_set["load_lb"], answer.basis_set["day"]) == (380.0, "Day 3")
    assert answer.flags == []
    assert BELOW_CHART_NOTE not in answer.answer


def test_a_model_that_never_stops_calling_tools_is_cut_off(tools):
    lookup = ModelTurn(tool_calls=(ToolCall("latest_top_set", {"lift": "squat"}),))
    answer, model = ask(tools, [lookup] * 8, "What was my last top squat?")
    assert len(model.seen) == 8
    assert answer.status == "answered"
    assert answer.answer.startswith("I found this logged set: Squat 1x5 at 380.0 lb")


def test_numbers_in_ignores_one_rep_max_cell_refs_and_list_numbers():
    text = "1. Your e1RM and 1RM are 441.8 lb\n2) from cell J5, block 3."
    assert numbers_in(text) == {441.8, 3.0}


def test_api_reports_when_the_model_is_not_running():
    class Down:
        def complete(self, messages, tools):
            raise ModelUnavailableError("Could not reach Ollama. Start it with `ollama serve`.")

    app.dependency_overrides[get_chat_model] = Down
    client = TestClient(app)
    response = client.post("/api/assistant/ask", json={"question": "What should I squat?"})
    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]

    # the pain check does not need the model
    hurt = client.post("/api/assistant/ask", json={"question": "my back hurts after deadlifts"})
    assert (hurt.status_code, hurt.json()["status"]) == (200, "referred")


@pytest.mark.skipif(
    not os.environ.get("KILOPLAN_LIVE_LLM"), reason="set KILOPLAN_LIVE_LLM=1 with Ollama running"
)
def test_example_question_with_the_real_model(tools):
    """Whatever the model does, the answer must be the right load or a question, never a guess."""
    answer = Assistant(OllamaModel(), tools).ask(EXAMPLE_QUESTION)
    assert unsupported_numbers(answer.answer, EXAMPLE_QUESTION, answer.calculations) == set()
    if answer.status == "answered" and answer.basis_set:
        assert answer.basis_set["sheet_cell"] == "J5"
        assert "368.2" in answer.answer
        assert BELOW_CHART_NOTE in answer.answer


def test_a_wrongly_called_tool_is_not_shown_to_the_lifter(tools):
    wrong = ModelTurn(tool_calls=(ToolCall("target_load", {"reps": 3, "target_rpe": 8}),))
    give_up = say("There was an internal error.")
    answer, model = ask(tools, [wrong, give_up, give_up], "Squat for 3 at RPE 8?")
    assert "Your tool call was wrong" in model.seen[-1][-1]["content"]
    assert answer.status == "needs_clarification"
    assert answer.flags == ["invalid_input"]
    assert answer.answer == NO_ANSWER


def test_a_wrong_call_can_be_corrected_by_the_model(tools):
    wrong = ModelTurn(tool_calls=(ToolCall("target_load", {"reps": 3, "target_rpe": 8}),))
    right = {"lift": "squat", "target_reps": 3, "target_rpe": 8}
    fixed = ModelTurn(tool_calls=(ToolCall("target_load", right),))
    answer, model = ask(tools, [wrong, fixed, say("Take 419.3 lb.")], "Squat for 3 at RPE 8?")
    assert "target_reps is required" in model.seen[1][-1]["content"]
    assert answer.status == "answered"
    assert answer.basis_set["load_lb"] == 380.0
    assert "Based on: Squat 1x5 at 380.0 lb (172.4 kg), RPE 7" in answer.answer


# The next tests replay mistakes a real 7B model made on these questions.


def test_a_calculation_is_pinned_to_the_set_the_lifter_named(tools):
    # the model found the 405 x 3 set, then asked for the lift's latest top set instead
    by_lift = {"lift": "squat", "target_reps": 2, "target_rpe": 5, "unit": "lb"}
    calculate = ModelTurn(tool_calls=(ToolCall("target_load", by_lift),))
    answer, _ = ask(tools, [FIND_THE_SET, calculate, say(GOOD_ANSWER)])
    assert answer.status == "answered"
    assert (answer.basis_set["load_lb"], answer.basis_set["sheet_cell"]) == (405.0, "J5")
    assert answer.calculations[1].result["target_load_lb"] == 368.2
    assert answer.calculations[1].arguments["set_id"] == answer.basis_set["set_id"]


def test_a_made_up_set_id_is_replaced_by_the_named_set(tools):
    lookup = ModelTurn(
        tool_calls=(
            ToolCall(
                "find_sets",
                {"lift": "squat", "variation": "paused", "week_number": 4, "stated_load": 365},
            ),
        )
    )
    made_up = {"set_id": 1, "lift": "squat", "variation": "paused", "target_reps": 1}
    calculate = ModelTurn(tool_calls=(ToolCall("target_load", {**made_up, "target_rpe": 8}),))
    answer, _ = ask(tools, [lookup, calculate, say("")], "Paused single at RPE 8?")
    assert answer.status == "answered"
    assert (answer.basis_set["movement"], answer.basis_set["load_lb"]) == ("Paused Squats", 365.0)


def test_a_made_up_set_id_with_no_lookup_is_dropped(tools):
    made_up = {"set_id": 999, "lift": "squat", "target_reps": 3, "target_rpe": 8}
    calculate = ModelTurn(tool_calls=(ToolCall("target_load", made_up),))
    answer, _ = ask(tools, [calculate, say("")], "What should I squat for 3 at RPE 8?")
    assert "set_id" not in answer.calculations[0].arguments
    assert (answer.status, answer.basis_set["load_lb"]) == ("answered", 380.0)

    no_basis = ModelTurn(
        tool_calls=(ToolCall("target_load", {"set_id": 7, "target_reps": 3, "target_rpe": 8}),)
    )
    answer, _ = ask(tools, [no_basis, say(""), say("")], "What should I take for 3 at RPE 8?")
    assert (answer.status, answer.flags) == ("needs_clarification", ["invalid_input"])


def test_a_set_found_for_one_lift_is_not_used_for_another(tools):
    bench = {"lift": "bench", "target_reps": 5, "target_rpe": 7}
    calculate = ModelTurn(tool_calls=(ToolCall("target_load", bench),))
    answer, _ = ask(tools, [FIND_THE_SET, calculate, say("")], "And bench for 5 at RPE 7?")
    assert "set_id" not in answer.calculations[1].arguments
    assert (answer.status, answer.flags) == ("needs_clarification", ["no_match"])


def test_a_logged_load_reported_as_a_max_is_sent_back(tools):
    lookup = ModelTurn(tool_calls=(ToolCall("latest_top_set", {"lift": "squat"}),))
    wrong = say("Your estimated one-rep max (1RM) is 380.0 lb (172.4 kg).")
    estimate = ModelTurn(tool_calls=(ToolCall("estimate_e1rm", {"lift": "squat"}),))
    answer, model = ask(
        tools,
        [lookup, wrong, estimate, say("Your estimated 1RM is 471.7 lb (214.0 kg).")],
        "What's my estimated squat max?",
    )
    assert "A logged set's load is not a one-rep max" in model.seen[2][-1]["content"]
    assert answer.status == "answered"
    assert "471.7 lb" in answer.answer
    assert "answer_corrected" in answer.flags


def test_a_max_that_is_never_calculated_is_not_passed_on(tools):
    lookup = ModelTurn(tool_calls=(ToolCall("latest_top_set", {"lift": "squat"}),))
    wrong = say("Your estimated one-rep max (1RM) is 380.0 lb (172.4 kg).")
    answer, _ = ask(tools, [lookup, wrong, wrong], "What's my estimated squat max?")
    assert answer.answer.startswith("I found this logged set: Squat 1x5 at 380.0 lb")
    assert "one-rep max" not in answer.answer


def test_an_answer_that_leaves_out_the_result_is_replaced(tools):
    vague = say("Take a bit less than your week 4 set of 405.")
    answer, model = ask(tools, [FIND_THE_SET, target_from_found_set, vague, vague])
    assert "must state the result: 368.2 lb (167.0 kg)" in model.seen[-1][-1]["content"]
    assert answer.answer.startswith("Take 368.2 lb (167.0 kg) for 2 reps at RPE 5.")


def test_a_stated_rpe_the_lifter_never_gave_is_not_checked_against_the_log(tools):
    # the lifter gave no RPE; the model made one up that disagrees with the logged 9
    lookup = ModelTurn(
        tool_calls=(
            ToolCall(
                "find_sets",
                {"lift": "squat", "week_number": 4, "reps": 3, "stated_load": 405, "stated_rpe": 8},
            ),
        )
    )
    question = "I took 405 for 3 on squat in week 4. What should I take for 2 reps at RPE 7?"

    def calculate(messages):
        found = json.loads(messages[-1]["content"])
        arguments = {"set_id": found["set"]["set_id"], "target_reps": 2, "target_rpe": 7}
        return ModelTurn(tool_calls=(ToolCall("target_load", arguments),))

    answer, _ = ask(tools, [lookup, calculate, say("")], question)
    assert "stated_rpe" not in answer.calculations[0].arguments
    assert answer.status == "answered"
    assert (answer.basis_set["load_lb"], answer.basis_set["rpe"]) == (405.0, "9")


def test_the_new_sets_reps_and_rpe_sent_under_the_wrong_names_still_work(tools):
    confused = {"lift": "squat", "stated_reps": 3, "stated_rpe": 8, "unit": "lb"}
    calculate = ModelTurn(tool_calls=(ToolCall("target_load", confused),))
    answer, _ = ask(tools, [calculate, say("")], "What should I squat for 3 reps at RPE 8?")
    assert answer.calculations[0].arguments == {
        "lift": "squat",
        "unit": "lb",
        "target_reps": 3,
        "target_rpe": 8,
    }
    assert answer.status == "answered"
    assert answer.answer.startswith("Take 419.3 lb (190.2 kg) for 3 reps at RPE 8.")
