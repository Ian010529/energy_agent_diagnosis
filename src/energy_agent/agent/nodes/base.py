from collections.abc import Awaitable, Callable
from typing import Protocol

from energy_agent.agent.state import DiagnosisState
from energy_agent.observability.tracing import Tracer

NodeUpdate = dict[str, object]
NodeCallable = Callable[[DiagnosisState], Awaitable[NodeUpdate]]
NodeLogCallable = Callable[
    [DiagnosisState, str, NodeUpdate | None, BaseException | None], Awaitable[None]
]


class AgentNode(Protocol):
    name: str

    async def __call__(self, state: DiagnosisState) -> NodeUpdate: ...


def traced_node(
    name: str,
    tracer: Tracer,
    node: NodeCallable,
    step_logger: NodeLogCallable | None = None,
) -> NodeCallable:
    async def wrapped(state: DiagnosisState) -> NodeUpdate:
        with tracer.start_span(
            f"agent.{name}",
            trace_id=state.trace_id,
            metadata={"session_id": state.session_id, "run_id": state.run_id},
        ) as span:
            try:
                result = await node(state)
            except Exception as exc:
                span.record_error(exc)
                if step_logger:
                    await step_logger(state, name, None, exc)
                raise
            span.set_output(result)
            if step_logger:
                await step_logger(state, name, result, None)
            return result

    return wrapped
