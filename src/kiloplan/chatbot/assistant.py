"""The program assistant: answers a lifter's questions about their own logged training.

The model only chooses tools and words the answer. Lookups, calculations and the
checks below are done in code:

- every number in an answer must come from a tool result or the lifter's question
- the logged set an answer is based on is always shown
- an RPE below the chart range is always disclosed
- a missing, ambiguous or conflicting lookup gets a question back, not a load
- a mention of pain or injury gets a referral, not load advice
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from kiloplan.chatbot.llm import ChatModel, Message, ModelTurn, ToolCall
from kiloplan.chatbot.tools import BELOW_CHART_NOTE, TOOL_SCHEMAS, ProgramTools

MAX_MODEL_TURNS = 8
LOOKUP_TOOLS = ("find_sets", "latest_top_set")
CALCULATION_TOOLS = ("estimate_e1rm", "target_load")

SYSTEM_PROMPT = """\
You are KiloPlan's program assistant for a powerlifter. You answer questions about the \
lifter's own logged training using the tools provided.

Rules:
- Never do arithmetic or unit conversion yourself, and never estimate. Every number you \
write must be copied exactly from a tool result or from the lifter's question.
- When the lifter describes a past set, first call find_sets and pass what they said \
(week_number, reps, stated_load, stated_rpe, unit). Then call target_load with that \
set_id plus target_reps and target_rpe.
- When the lifter names no past set, call target_load with lift, target_reps and \
target_rpe. It uses their latest top set.
- target_reps and target_rpe are the new set the lifter is about to do, never the past set.
- For a question about their max or e1RM, call estimate_e1rm with lift. A logged set's \
load is not a one-rep max.
- If a tool result's status is not "ok", do not give a load. Tell the lifter what the \
tool found and ask them what to do.
- Say which logged set the answer is based on.
- Do not swap in a different lift variation without asking.
- Keep the answer to a few sentences, in the unit the lifter used.
- A single is 1 rep, a double is 2 and a triple is 3.

Examples of the right tool calls:
- "What should I bench for 5 at RPE 7?" -> target_load(lift="bench", target_reps=5, \
target_rpe=7)
- "What should I take for a paused squat triple at RPE 8?" -> target_load(lift="squat", \
variation="paused", target_reps=3, target_rpe=8)
- "I did 300 for 4 on bench in week 2 at RPE 8. What should I take for 6 at RPE 7?" -> \
find_sets(lift="bench", week_number=2, reps=4, stated_load=300, stated_rpe=8), then \
target_load(set_id=<the set_id it returned>, target_reps=6, target_rpe=7)
- "What is my deadlift max?" -> estimate_e1rm(lift="deadlift")
"""

PAIN_WORDS = re.compile(
    # "pulled" and "sharp" are left out: lifters pull deadlifts and bars are sharp
    r"\b(pain\w*|hurt\w*|injur\w*|tweak\w*|strain\w*|sprain\w*|torn|tear|numb\w*|"
    r"tingl\w*|swollen|swelling|pinch\w*|ach(e|es|ing))\b",
    re.IGNORECASE,
)
PAIN_REFERRAL = (
    "I can't give load advice when pain or a possible injury is involved. Please see a "
    "qualified professional, such as a physiotherapist or sports medicine doctor, before "
    "training through it."
)
NOT_CHECKED_NOTE = "This uses the numbers you gave me; it was not checked against your log."
NO_ANSWER = (
    "I couldn't work that out from your logged training. Which lift is it, and which past "
    "set (load, reps and RPE) should I base it on?"
)

# a number not glued to a letter on its left (so not the 1 in "e1RM" or the 5 in "J5")
NUMBER = re.compile(r"(?<![A-Za-z\d.])\d+(?:\.\d+)?")
ONE_REP_MAX = re.compile(r"\b1\s*-?\s*(rm|rep max)\b", re.IGNORECASE)
MAX_CLAIM = re.compile(r"\b(e1rm|1\s*-?\s*rm|one[- ]rep max|max)\b", re.IGNORECASE)
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


@dataclass
class Calculation:
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass
class AssistantAnswer:
    """`status` is answered, needs_clarification or referred."""

    status: str
    answer: str
    basis_set: dict[str, Any] | None = None
    calculations: list[Calculation] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def mentions_pain(text: str) -> bool:
    return bool(PAIN_WORDS.search(text))


def numbers_in(text: str) -> set[float]:
    """The numbers written in a piece of text, ignoring "1RM" and list numbering."""
    cleaned = LIST_MARKER.sub("", ONE_REP_MAX.sub("", text))
    return {float(match) for match in NUMBER.findall(cleaned)}


def _numbers_in_value(value: object) -> set[float]:
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, int | float):
        return {float(value)}
    if isinstance(value, str):
        return numbers_in(value)
    if isinstance(value, dict):
        return set().union(*(_numbers_in_value(item) for item in value.values()))
    if isinstance(value, list | tuple):
        return set().union(*(_numbers_in_value(item) for item in value))
    return set()


def unsupported_numbers(answer: str, question: str, calculations: list[Calculation]) -> set[float]:
    """Numbers in the answer that came from neither the question nor any tool result."""
    allowed = numbers_in(question)
    for calculation in calculations:
        allowed |= _numbers_in_value(calculation.result)
    return numbers_in(answer) - allowed


def answer_problems(text: str, question: str, calculations: list[Calculation]) -> list[str]:
    """What is wrong with a drafted answer, as instructions for the model to fix it."""
    if not text:
        return []
    problems = []
    invented = unsupported_numbers(text, question, calculations)
    if invented:
        listed = ", ".join(f"{number:g}" for number in sorted(invented))
        problems.append(
            f"Your answer used numbers that are not in any tool result: {listed}. Use only "
            "numbers copied exactly from the tool results. Do not round."
        )
    calculated = [
        calc
        for calc in calculations
        if calc.tool in CALCULATION_TOOLS and calc.result.get("status") == "ok"
    ]
    written = numbers_in(text)
    if not calculated and written and MAX_CLAIM.search(text):
        problems.append(
            "You gave a one-rep max without calculating it. A logged set's load is not a "
            "one-rep max. Call estimate_e1rm with the lift or set_id and report its e1rm."
        )
    if calculated:
        result = calculated[-1].result
        key = "target_load" if calculated[-1].tool == "target_load" else "e1rm"
        if not written & {result[f"{key}_lb"], result[f"{key}_kg"]}:
            problems.append(f"Your answer must state the result: {result[f'{key}_text']}.")
    return problems


class Assistant:
    def __init__(self, model: ChatModel, tools: ProgramTools) -> None:
        self.model = model
        self.tools = tools

    def ask(self, question: str) -> AssistantAnswer:
        if mentions_pain(question):
            return AssistantAnswer(
                status="referred", answer=PAIN_REFERRAL, flags=["pain_or_injury"]
            )

        messages: list[Message] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        calculations: list[Calculation] = []
        flags: list[str] = []
        text = self._run(messages, calculations, question)

        blocked = self._blocking_result(calculations)
        if blocked and blocked.get("status") == "invalid_input":
            problems = [
                f"Your tool call was wrong and nothing was calculated. {blocked['message']}"
            ]
        else:
            problems = [] if blocked else answer_problems(text, question, calculations)
        if problems:
            # one chance to put it right, by rewriting or by calling the tool it skipped
            flags.append("answer_corrected")
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": " ".join(problems)})
            text = self._run(messages, calculations, question)
            blocked = self._blocking_result(calculations)
            if not blocked and answer_problems(text, question, calculations):
                text = ""

        if blocked:
            return self._clarification(text, question, calculations, blocked)
        return self._answered(text, calculations, flags)

    def _run(self, messages: list[Message], calculations: list[Calculation], question: str) -> str:
        """Let the model call tools until it writes an answer. Returns that text."""
        for _ in range(MAX_MODEL_TURNS):
            turn: ModelTurn = self.model.complete(messages, TOOL_SCHEMAS)
            if not turn.tool_calls:
                return turn.text.strip()
            messages.append(
                {"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls}
            )
            for call in turn.tool_calls:
                arguments = self._checked_arguments(call, calculations, question)
                result = self.tools.call(call.name, arguments)
                calculations.append(Calculation(call.name, arguments, result))
                messages.append(
                    {"role": "tool", "tool_name": call.name, "content": json.dumps(result)}
                )
        return ""

    @staticmethod
    def _checked_arguments(
        call: ToolCall, calculations: list[Calculation], question: str
    ) -> dict[str, Any]:
        """The arguments a tool actually runs with.

        Small models make up what the lifter "said", ignore the set they just looked
        up, or invent a set_id. So a stated load or RPE that is not in the question is
        dropped; once find_sets has found the set the lifter named, calculations for
        that lift use it; and a set_id no lookup returned is never used.
        """
        arguments = dict(call.arguments)
        asked = numbers_in(question)
        for key in ("stated_load", "stated_rpe", "stated_reps"):
            value = arguments.get(key)
            if isinstance(value, int | float) and float(value) not in asked:
                del arguments[key]
        if call.name == "target_load" and "stated_load" not in arguments:
            # the new set's reps and RPE sent under the past set's names
            for stated, target in (("stated_reps", "target_reps"), ("stated_rpe", "target_rpe")):
                if stated in arguments and target not in arguments:
                    arguments[target] = arguments.pop(stated)
        if call.name not in CALCULATION_TOOLS:
            return arguments
        known_ids: set[int] = set()
        named: dict[str, Any] | None = None
        for calculation in calculations:
            if calculation.tool not in LOOKUP_TOOLS:
                continue
            result = calculation.result
            listed = [result[key] for key in ("set",) if key in result]
            for key in ("matching_sets", "logged_sets", "sets_in_that_week"):
                listed += result.get(key, [])
            known_ids.update(item["set_id"] for item in listed)
            if calculation.tool == "find_sets":
                named = result["set"] if result.get("status") == "ok" else None
        if arguments.get("set_id") in known_ids:
            return arguments
        arguments.pop("set_id", None)
        if named and arguments.get("lift") in (None, "", named["lift"]):
            arguments["set_id"] = named["set_id"]
        return arguments

    @staticmethod
    def _blocking_result(calculations: list[Calculation]) -> dict[str, Any] | None:
        """The failed lookup or calculation that should stop a load being given, if any.

        A failed lookup is cleared only by a later successful lookup, never by
        calculating from numbers the log did not confirm. A failed calculation is
        cleared by a later successful one.
        """
        failed_lookup: dict[str, Any] | None = None
        failed_calculation: dict[str, Any] | None = None
        for calculation in calculations:
            failure = None if calculation.result.get("status") == "ok" else calculation.result
            if calculation.tool in LOOKUP_TOOLS:
                failed_lookup = failure
            else:
                failed_calculation = failure
        return failed_lookup or failed_calculation

    def _clarification(
        self,
        text: str,
        question: str,
        calculations: list[Calculation],
        blocked: dict[str, Any],
    ) -> AssistantAnswer:
        """No load is given. The model's wording is kept only if it adds no numbers."""
        found = (
            blocked.get("logged_sets")
            or blocked.get("matching_sets")
            or blocked.get("sets_in_that_week")
            or ([blocked["set"]] if "set" in blocked else [])
        )
        lookups_only = [calc for calc in calculations if calc.tool in LOOKUP_TOOLS]
        if blocked.get("status") == "invalid_input":
            # a tool was called wrongly: that is the model's mistake, not the lifter's
            text = NO_ANSWER
        elif not text or unsupported_numbers(text, question, lookups_only):
            lines = [blocked.get("message", NO_ANSWER)]
            if found:
                lines.append("Logged: " + "; ".join(item["description"] for item in found))
            variations = blocked.get("variations_with_data")
            if variations:
                lines.append("Variations with logged sets: " + ", ".join(variations) + ".")
            lines.append("Which set should I use?")
            text = "\n".join(lines)
        return AssistantAnswer(
            status="needs_clarification",
            answer=text,
            calculations=calculations,
            flags=[blocked.get("status", "no_match")],
        )

    @staticmethod
    def _template(calculations: list[Calculation]) -> str:
        """A plain answer written from the tool results, for when the model's cannot be used."""
        for calculation in reversed(calculations):
            result = calculation.result
            if result.get("status") != "ok":
                continue
            if calculation.tool == "target_load":
                target = result["target"]
                return (
                    f"Take {result['target_load_text']} for {target['reps']:g} reps at RPE "
                    f"{target['rpe']:g}. That uses an estimated 1RM of {result['e1rm_text']}."
                )
            if calculation.tool == "estimate_e1rm":
                return f"Your estimated 1RM is {result['e1rm_text']}."
            if calculation.tool in LOOKUP_TOOLS:
                return f"I found this logged set: {result['set']['description']}."
        return ""

    def _answered(
        self, text: str, calculations: list[Calculation], flags: list[str]
    ) -> AssistantAnswer:
        text = text or self._template(calculations)
        if not text:
            return AssistantAnswer(
                status="needs_clarification",
                answer=NO_ANSWER,
                calculations=calculations,
                flags=[*flags, "no_tool_result"],
            )
        successes = [calc.result for calc in calculations if calc.result.get("status") == "ok"]
        basis = next((result["set"] for result in reversed(successes) if "set" in result), None)
        if basis and basis["description"] not in text:
            text += f"\n\nBased on: {basis['description']}."
        if basis is None and any("based_on" in result for result in successes):
            flags.append("not_checked_against_log")
            text += f"\n\n{NOT_CHECKED_NOTE}"
        if any(result.get("below_chart_range") for result in successes):
            flags.append("below_chart_range")
            if BELOW_CHART_NOTE not in text:
                text += f"\n\nNote: {BELOW_CHART_NOTE}"
        return AssistantAnswer(
            status="answered", answer=text, basis_set=basis, calculations=calculations, flags=flags
        )
