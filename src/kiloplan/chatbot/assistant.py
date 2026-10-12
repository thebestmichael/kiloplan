"""The program assistant: answers a lifter's questions about their own logged training.

The model only chooses tools and words the answer. Lookups, calculations and the
checks below are done in code:

- every number in an answer must come from a tool result or the conversation so far
- the logged set an answer is based on is always shown
- an RPE below the chart range is always disclosed
- a missing, ambiguous or conflicting lookup gets a question back, not a load
- a mention of pain or injury gets a referral, not load advice
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from kiloplan.chatbot.llm import ChatModel, Message, ModelTurn
from kiloplan.chatbot.toolbox import CALCULATION, LOOKUP, Toolbox
from kiloplan.chatbot.tools import BELOW_CHART_NOTE

MAX_MODEL_TURNS = 8

# the rules every tool group shares; each group adds its own through the toolbox
SYSTEM_PROMPT = """\
You are KiloPlan's assistant for a powerlifter. You answer questions about the lifter's \
own logged training using the tools provided.

Rules:
- Never do arithmetic or unit conversion yourself, and never estimate. Every number you \
write must be copied exactly from a tool result or from the lifter's question.
- If a tool result's status is not "ok", do not give a number. Tell the lifter what the \
tool found and ask them what to do.
- Say which logged set the answer is based on.
- Keep the answer to a few sentences, in the unit the lifter used.
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
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


@dataclass(frozen=True)
class Turn:
    """An earlier message of the conversation. `role` is user or assistant."""

    role: str
    content: str


@dataclass
class Calculation:
    """One tool call and its result. `kind` is the tool's: lookup or calculation."""

    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    kind: str = CALCULATION


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


class Assistant:
    def __init__(self, model: ChatModel, toolbox: Toolbox) -> None:
        self.model = model
        self.toolbox = toolbox

    def ask(self, question: str, history: Sequence[Turn] = ()) -> AssistantAnswer:
        """Answer a question. `history` is the conversation before it, oldest first.

        Nothing is remembered between calls: tool results from earlier turns are gone,
        so a follow-up looks its sets up again.
        """
        asked = [turn.content for turn in history if turn.role == "user"] + [question]
        if any(mentions_pain(text) for text in asked):
            return AssistantAnswer(
                status="referred", answer=PAIN_REFERRAL, flags=["pain_or_injury"]
            )

        messages: list[Message] = [
            {"role": "system", "content": SYSTEM_PROMPT + self.toolbox.instructions},
            *({"role": turn.role, "content": turn.content} for turn in history),
            {"role": "user", "content": question},
        ]
        # earlier answers were checked when they were given, so their numbers may be repeated
        question = "\n".join([*(turn.content for turn in history), question])
        calculations: list[Calculation] = []
        text = self._run(messages, calculations)

        blocked = self._blocking_call(calculations)
        if blocked:
            return self._clarification(text, question, calculations, blocked)

        flags: list[str] = []
        if unsupported_numbers(text, question, calculations):
            flags.append("answer_corrected")
            text = self._retry(messages, text, question, calculations)
        return self._answered(text, calculations, flags)

    def _run(self, messages: list[Message], calculations: list[Calculation]) -> str:
        """Let the model call tools until it writes an answer. Returns that text."""
        for _ in range(MAX_MODEL_TURNS):
            turn: ModelTurn = self.model.complete(messages, self.toolbox.schemas)
            if not turn.tool_calls:
                return turn.text.strip()
            messages.append(
                {"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls}
            )
            for call in turn.tool_calls:
                result = self.toolbox.call(call.name, call.arguments)
                tool = self.toolbox.get(call.name)
                kind = tool.kind if tool else CALCULATION
                calculations.append(Calculation(call.name, call.arguments, result, kind))
                messages.append(
                    {"role": "tool", "tool_name": call.name, "content": json.dumps(result)}
                )
        return ""

    @staticmethod
    def _blocking_call(calculations: list[Calculation]) -> Calculation | None:
        """The failed lookup or calculation that should stop an answer being given, if any.

        A failed lookup is cleared only by a later successful lookup, never by
        calculating from numbers the log did not confirm. A failed calculation is
        cleared by a later successful one.
        """
        failed_lookup: Calculation | None = None
        failed_calculation: Calculation | None = None
        for calculation in calculations:
            failure = None if calculation.result.get("status") == "ok" else calculation
            if calculation.kind == LOOKUP:
                failed_lookup = failure
            else:
                failed_calculation = failure
        return failed_lookup or failed_calculation

    def _clarification(
        self,
        text: str,
        question: str,
        calculations: list[Calculation],
        blocked: Calculation,
    ) -> AssistantAnswer:
        """No answer is given. The model's wording is kept only if it adds no numbers."""
        lookups_only = [calc for calc in calculations if calc.kind == LOOKUP]
        if not text or unsupported_numbers(text, question, lookups_only):
            tool = self.toolbox.get(blocked.tool)
            if tool and tool.explain and "message" in blocked.result:
                text = tool.explain(blocked.result)
            else:
                text = blocked.result.get("message", NO_ANSWER)
        return AssistantAnswer(
            status="needs_clarification",
            answer=text,
            calculations=calculations,
            flags=[blocked.result.get("status", "no_match")],
        )

    def _retry(
        self,
        messages: list[Message],
        text: str,
        question: str,
        calculations: list[Calculation],
    ) -> str:
        """One chance to rewrite an answer containing numbers no tool produced."""
        bad = ", ".join(
            f"{number:g}" for number in sorted(unsupported_numbers(text, question, calculations))
        )
        messages.append({"role": "assistant", "content": text})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Your answer used numbers that are not in any tool result: {bad}. Rewrite "
                    "it using only numbers copied exactly from the tool results. Do not round."
                ),
            }
        )
        rewritten = self._run(messages, calculations)
        if rewritten and not unsupported_numbers(rewritten, question, calculations):
            return rewritten
        return ""

    def _template(self, calculations: list[Calculation]) -> str:
        """A plain answer written from the tool results, for when the model's cannot be used."""
        for calculation in reversed(calculations):
            tool = self.toolbox.get(calculation.tool)
            if calculation.result.get("status") == "ok" and tool and tool.summarize:
                return tool.summarize(calculation.result)
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
