from collections.abc import Awaitable, Callable
from datetime import datetime
from time import monotonic
from typing import Protocol

from energy_agent.agent.state import DiagnosisState
from energy_agent.observability.metrics import NODE_DURATION, NODE_TOTAL
from energy_agent.observability.tracing import Tracer

NodeUpdate = dict[str, object]
NodeCallable = Callable[[DiagnosisState], Awaitable[NodeUpdate]]
NodeLogCallable = Callable[
    [
        DiagnosisState,
        str,
        NodeUpdate | None,
        BaseException | None,
        datetime,
        datetime,
        int,
    ],
    Awaitable[None],
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
        from energy_agent.core.time import utc_now

        started_at = utc_now()
        started = monotonic()
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
                    ended_at = utc_now()
                    await step_logger(
                        state,
                        name,
                        None,
                        exc,
                        started_at,
                        ended_at,
                        max(0, int((monotonic() - started) * 1000)),
                    )
                NODE_TOTAL.labels(node=name, status="failed").inc()
                NODE_DURATION.labels(node=name, status="failed").observe(monotonic() - started)
                raise
            span.set_output(result)
            if step_logger:
                ended_at = utc_now()
                await step_logger(
                    state,
                    name,
                    result,
                    None,
                    started_at,
                    ended_at,
                    max(0, int((monotonic() - started) * 1000)),
                )
            NODE_TOTAL.labels(node=name, status="ok").inc()
            NODE_DURATION.labels(node=name, status="ok").observe(monotonic() - started)
            return result

    return wrapped
