"""The language model behind the assistant, kept behind one small interface.

`ChatModel` is all the assistant knows about a model, so providers can be swapped.
`OllamaModel` talks to a local Ollama server; `ScriptedModel` replays fixed turns for
tests.
"""

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import ollama

DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"

# {"role": "system" | "user" | "assistant" | "tool", "content": str}, where an assistant
# message may carry "tool_calls" and a tool message carries "tool_name"
Message = dict[str, Any]


class ModelUnavailableError(RuntimeError):
    """The model could not be reached or is not installed."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    """One reply from the model: text, or requests to call tools."""

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


class ChatModel(Protocol):
    def complete(self, messages: Sequence[Message], tools: Sequence[dict[str, Any]]) -> ModelTurn:
        """Continue the conversation. `tools` are name/description/parameters schemas."""
        ...


class OllamaModel:
    """A local model served by Ollama. Reads KILOPLAN_LLM_MODEL and OLLAMA_HOST."""

    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        self.model = model or os.environ.get("KILOPLAN_LLM_MODEL", DEFAULT_OLLAMA_MODEL)
        self.client = ollama.Client(host=host or os.environ.get("OLLAMA_HOST"))

    def complete(self, messages: Sequence[Message], tools: Sequence[dict[str, Any]]) -> ModelTurn:
        try:
            response = self.client.chat(
                model=self.model,
                messages=[self._to_ollama(message) for message in messages],
                tools=[{"type": "function", "function": tool} for tool in tools],
                options={"temperature": 0},
            )
        except ollama.ResponseError as error:
            message = f"Ollama could not run {self.model!r}: {error.error}"
            raise ModelUnavailableError(message) from error
        except (ConnectionError, OSError) as error:
            message = "Could not reach Ollama. Start it with `ollama serve`."
            raise ModelUnavailableError(message) from error
        calls = tuple(
            ToolCall(call.function.name, dict(call.function.arguments))
            for call in response.message.tool_calls or ()
        )
        return ModelTurn(text=response.message.content or "", tool_calls=calls)

    @staticmethod
    def _to_ollama(message: Message) -> Message:
        converted = {key: value for key, value in message.items() if key != "tool_calls"}
        if message.get("tool_calls"):
            converted["tool_calls"] = [
                {"function": {"name": call.name, "arguments": call.arguments}}
                for call in message["tool_calls"]
            ]
        return converted


ScriptStep = ModelTurn | Callable[[Sequence[Message]], ModelTurn]


@dataclass
class ScriptedModel:
    """Replays fixed turns in order. A step may be a function of the messages so far."""

    steps: list[ScriptStep]
    seen: list[list[Message]] = field(default_factory=list)

    def complete(self, messages: Sequence[Message], tools: Sequence[dict[str, Any]]) -> ModelTurn:
        self.seen.append(list(messages))
        if not self.steps:
            raise AssertionError("the scripted model was asked for more turns than it has")
        step = self.steps.pop(0)
        return step(messages) if callable(step) else step
