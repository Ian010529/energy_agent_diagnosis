from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass

from pydantic import BaseModel

from energy_agent.tools.contracts import ToolResult

ToolHandler = Callable[[BaseModel], Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class ToolRegistration:
    schema: type[BaseModel]
    handler: ToolHandler
    dependency: str | None = None
    read_only: bool = True
    requires_human_action: bool = False

    def __iter__(self) -> Iterator[object]:
        yield self.schema
        yield self.handler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolRegistration] = {}

    def register(
        self,
        name: str,
        schema: type[BaseModel],
        handler: ToolHandler,
        *,
        dependency: str | None = None,
        read_only: bool = True,
        requires_human_action: bool = False,
    ) -> None:
        self._tools[name] = ToolRegistration(
            schema=schema,
            handler=handler,
            dependency=dependency,
            read_only=read_only,
            requires_human_action=requires_human_action,
        )

    def get(self, name: str) -> ToolRegistration | None:
        return self._tools.get(name)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)
