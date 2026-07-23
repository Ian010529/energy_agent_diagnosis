from energy_agent.indexing.contracts import IndexJobMessage
from energy_agent.indexing.handler_runtime import HandlerResult, IndexHandlerRuntime


class ManualIndexHandler:
    def __init__(self, runtime: IndexHandlerRuntime) -> None:
        self.runtime = runtime

    async def handle(self, event: IndexJobMessage) -> HandlerResult:
        return await self.runtime.handle(event)

    async def handle_batch(self, events: list[IndexJobMessage]) -> dict[str, HandlerResult]:
        return await self.runtime.handle_batch(events)
