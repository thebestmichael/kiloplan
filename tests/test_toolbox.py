"""A second tool group, as nutrition will be, used through the assistant unchanged."""

import pytest

from kiloplan.chatbot.assistant import Assistant
from kiloplan.chatbot.llm import ModelTurn, ScriptedModel, ToolCall
from kiloplan.chatbot.toolbox import CALCULATION, LOOKUP, Tool, Toolbox

NO_PARAMETERS = {"type": "object", "properties": {}, "required": []}


class MealTools:
    instructions = "- For food questions, call find_meal first.\n"

    def __init__(self, meals):
        self.meals = meals

    def find_meal(self, name: str):
        if name not in self.meals:
            return {"status": "no_match", "message": f"No meal called {name} is logged."}
        return {"status": "ok", "set": {"description": f"{name} on 2026-04-08"}, "meal": name}

    def protein_total(self, name: str):
        return {"status": "ok", "protein_g": self.meals[name]}

    def tools(self):
        return [
            Tool(
                name="find_meal",
                description="Look up a logged meal.",
                parameters=NO_PARAMETERS,
                kind=LOOKUP,
                handler=self.find_meal,
            ),
            Tool(
                name="protein_total",
                description="Protein in a logged meal.",
                parameters=NO_PARAMETERS,
                kind=CALCULATION,
                handler=self.protein_total,
                summarize=lambda result: f"That meal had {result['protein_g']} g of protein.",
            ),
        ]


def call(tool, **arguments):
    return ModelTurn(tool_calls=(ToolCall(tool, arguments),))


def ask(steps, question="How much protein was in my lunch?"):
    model = ScriptedModel(list(steps))
    toolbox = Toolbox(MealTools({"lunch": 42.5}))
    return Assistant(model, toolbox).ask(question), model


def test_a_new_group_is_offered_to_the_model_with_its_instructions():
    _, model = ask([ModelTurn(text="Which meal?")])
    system = model.seen[0][0]["content"]
    assert "call find_meal first" in system
    assert "Never do arithmetic" in system


def test_a_new_groups_tools_answer_through_the_assistant():
    steps = [
        call("find_meal", name="lunch"),
        call("protein_total", name="lunch"),
        ModelTurn(text="Your lunch had 42.5 g of protein."),
    ]
    answer, _ = ask(steps)
    assert answer.status == "answered"
    assert [(calc.tool, calc.kind) for calc in answer.calculations] == [
        ("find_meal", "lookup"),
        ("protein_total", "calculation"),
    ]
    assert answer.answer == ("Your lunch had 42.5 g of protein.\n\nBased on: lunch on 2026-04-08.")


def test_a_number_the_new_tools_did_not_produce_is_replaced_by_their_summary():
    steps = [
        call("find_meal", name="lunch"),
        call("protein_total", name="lunch"),
        ModelTurn(text="About 45 g."),
        ModelTurn(text="Roughly 45 g."),
    ]
    answer, _ = ask(steps)
    assert answer.flags == ["answer_corrected"]
    assert answer.answer.startswith("That meal had 42.5 g of protein.")
    assert "45" not in answer.answer


def test_a_failed_lookup_in_a_new_group_blocks_the_answer():
    steps = [
        call("find_meal", name="dinner"),
        call("protein_total", name="lunch"),
        ModelTurn(text="It had 42.5 g of protein."),
    ]
    answer, _ = ask(steps, "How much protein was in my dinner?")
    assert answer.status == "needs_clarification"
    assert answer.flags == ["no_match"]
    assert answer.answer == "No meal called dinner is logged."


def test_schemas_list_every_tool_of_every_group():
    class Other:
        instructions = ""

        def tools(self):
            return [Tool("ping", "Ping.", NO_PARAMETERS, LOOKUP, lambda: {"status": "ok"})]

    toolbox = Toolbox(MealTools({}), Other())
    assert [schema["name"] for schema in toolbox.schemas] == [
        "find_meal",
        "protein_total",
        "ping",
    ]
    assert toolbox.schemas[0] == {
        "name": "find_meal",
        "description": "Look up a logged meal.",
        "parameters": NO_PARAMETERS,
    }
    assert toolbox.call("ping", {}) == {"status": "ok"}


def test_two_groups_cannot_share_a_tool_name():
    with pytest.raises(ValueError, match="two tools are named 'find_meal'"):
        Toolbox(MealTools({}), MealTools({}))
