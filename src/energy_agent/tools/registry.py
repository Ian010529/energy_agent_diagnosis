from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from energy_agent.tools.contracts import ToolResult

ToolHandler = Callable[[BaseModel], Awaitable[ToolResult]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[type[BaseModel], ToolHandler]] = {}

    def register(self, name: str, schema: type[BaseModel], handler: ToolHandler) -> None:
        self._tools[name] = (schema, handler)

    def get(self, name: str) -> tuple[type[BaseModel], ToolHandler] | None:
        return self._tools.get(name)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)
