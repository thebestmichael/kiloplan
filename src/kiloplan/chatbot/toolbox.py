"""The registry of tools the assistant can call.

A feature adds tools by providing a group: an object with a `tools()` method. The
assistant only ever sees a `Toolbox`, so new groups need no change to the assistant.

Every tool returns a dict, and the assistant relies on these keys:

- `status`: "ok", or a failure such as "no_match", "ambiguous" or "conflict"
- `message`: what went wrong, when the status is not "ok"
- `set`: the logged record the result is based on, with a `description` to show
- `based_on`: the inputs of a calculation, logged or stated
- `below_chart_range`: True when the result is an extrapolation that must be disclosed
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

Result = dict[str, Any]

# a lookup reads the lifter's stored data; a calculation computes from it
LOOKUP = "lookup"
CALCULATION = "calculation"


@dataclass(frozen=True)
class Tool:
    """One callable tool.

    `summarize` words a successful result as a plain sentence, and `explain` words a
    failed one, for when the model's own wording cannot be used.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    kind: str
    handler: Callable[..., Result]
    summarize: Callable[[Result], str] | None = None
    explain: Callable[[Result], str] | None = None

    @property
    def schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


class ToolGroup(Protocol):
    """A feature's tools, plus the rules it adds to the model's instructions."""

    instructions: str

    def tools(self) -> list[Tool]: ...


class Toolbox:
    """The tools of one or more groups, for one lifter."""

    def __init__(self, *groups: ToolGroup) -> None:
        self._tools: dict[str, Tool] = {}
        self.instructions = "".join(group.instructions for group in groups)
        for group in groups:
            for tool in group.tools():
                if tool.name in self._tools:
                    raise ValueError(f"two tools are named {tool.name!r}")
                self._tools[tool.name] = tool

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema for tool in self._tools.values()]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def call(self, name: str, arguments: dict[str, Any]) -> Result:
        """Run a tool by name. Bad names and arguments come back as results, not exceptions."""
        tool = self.get(name)
        if tool is None:
            return {"status": "invalid_input", "message": f"Unknown tool {name!r}."}
        try:
            return tool.handler(
                **{key: value for key, value in arguments.items() if value is not None}
            )
        except (TypeError, ValueError) as error:
            return {"status": "invalid_input", "message": str(error)}
