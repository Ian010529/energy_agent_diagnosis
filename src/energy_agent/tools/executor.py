import asyncio
from time import monotonic

from pydantic import ValidationError

from energy_agent.observability.tracing import Tracer
from energy_agent.tools.contracts import ToolMeta, ToolResult, ToolStatus
from energy_agent.tools.policies import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TOOL_CALLS_PER_RUN,
)
from energy_agent.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, tracer: Tracer) -> None:
        self.registry = registry
        self.tracer = tracer
        self.calls = 0

    async def execute(self, name: str, arguments: dict[str, object], trace_id: str) -> ToolResult:
        self.calls += 1
        if self.calls > MAX_TOOL_CALLS_PER_RUN:
            return self._failure(trace_id, "TOOL_BUDGET_EXCEEDED", ToolStatus.FAILED)
        registered = self.registry.get(name)
        if registered is None:
            return self._failure(trace_id, "TOOL_NOT_AVAILABLE", ToolStatus.DEGRADED)
        schema, handler = registered
        try:
            payload = schema.model_validate(arguments)
        except ValidationError:
            return self._failure(trace_id, "TOOL_ARGUMENT_INVALID", ToolStatus.FAILED)
        started = monotonic()
        with self.tracer.start_span(
            f"tool.{name}", trace_id=trace_id, metadata={"tool": name}
        ) as span:
            for attempt in range(1, DEFAULT_MAX_ATTEMPTS + 1):
                try:
                    result = await asyncio.wait_for(handler(payload), DEFAULT_TIMEOUT_SECONDS)
                    result.meta.attempts = attempt
                    result.meta.latency_ms = int((monotonic() - started) * 1000)
                    span.set_output(
                        {
                            "status": result.status,
                            "attempts": attempt,
                            "latency_ms": result.meta.latency_ms,
                        }
                    )
                    return result
                except (TimeoutError, ConnectionError) as exc:
                    if attempt == DEFAULT_MAX_ATTEMPTS:
                        status = (
                            ToolStatus.TIMEOUT
                            if isinstance(exc, TimeoutError)
                            else ToolStatus.DEGRADED
                        )
                        return self._failure(trace_id, "TOOL_TIMEOUT", status, attempts=attempt)
                except Exception:
                    return self._failure(trace_id, "TOOL_PROVIDER_FAILED", ToolStatus.FAILED)
        return self._failure(trace_id, "TOOL_PROVIDER_FAILED", ToolStatus.FAILED)

    @staticmethod
    def _failure(trace_id: str, code: str, status: ToolStatus, attempts: int = 1) -> ToolResult:
        return ToolResult(
            success=False,
            status=status,
            meta=ToolMeta(
                trace_id=trace_id,
                source_system="energy-agent",
                attempts=attempts,
                retryable=status in {ToolStatus.TIMEOUT, ToolStatus.DEGRADED},
            ),
            error_code=code,
            error_message=code,
        )
