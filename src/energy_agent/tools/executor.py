import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from time import monotonic

from pydantic import ValidationError

from energy_agent.core.time import utc_now
from energy_agent.observability.metrics import TOOL_CALLS, TOOL_DURATION
from energy_agent.observability.tracing import Tracer
from energy_agent.reliability.circuit_breaker import CircuitOpenError
from energy_agent.reliability.registry import CircuitBreakerRegistry
from energy_agent.tools.contracts import ToolMeta, ToolResult, ToolStatus
from energy_agent.tools.policies import (
    DEFAULT_MAX_ATTEMPTS,
    MAX_TOOL_CALLS_PER_RUN,
    timeout_seconds_for,
)
from energy_agent.tools.registry import ToolRegistry

ToolLogCallable = Callable[[str, ToolResult, datetime, datetime], Awaitable[None]]


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        tracer: Tracer,
        tool_logger: ToolLogCallable | None = None,
        circuit_breakers: CircuitBreakerRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.tracer = tracer
        self.calls = 0
        self.tool_logger = tool_logger
        self.circuit_breakers = circuit_breakers

    async def execute(self, name: str, arguments: dict[str, object], trace_id: str) -> ToolResult:
        self.calls += 1
        if self.calls > MAX_TOOL_CALLS_PER_RUN:
            return self._failure(trace_id, "TOOL_BUDGET_EXCEEDED", ToolStatus.FAILED)
        registered = self.registry.get(name)
        if registered is None:
            return self._failure(trace_id, "TOOL_NOT_AVAILABLE", ToolStatus.DEGRADED)
        try:
            payload = registered.schema.model_validate(arguments)
        except ValidationError:
            return self._failure(trace_id, "TOOL_ARGUMENT_INVALID", ToolStatus.FAILED)
        dependency = registered.dependency
        breaker = (
            self.circuit_breakers.get(dependency) if dependency and self.circuit_breakers else None
        )
        if breaker:
            try:
                breaker.allow()
            except CircuitOpenError:
                return self._failure(trace_id, "CIRCUIT_OPEN", ToolStatus.DEGRADED)
        started = monotonic()
        started_at = utc_now()
        timeout_seconds = timeout_seconds_for(name)
        with self.tracer.start_span(
            f"tool.{name}", trace_id=trace_id, metadata={"tool": name}
        ) as span:
            for attempt in range(1, DEFAULT_MAX_ATTEMPTS + 1):
                try:
                    result = await asyncio.wait_for(registered.handler(payload), timeout_seconds)
                    result.meta.attempts = attempt
                    result.meta.latency_ms = int((monotonic() - started) * 1000)
                    span.set_output(
                        {
                            "status": result.status,
                            "attempts": attempt,
                            "latency_ms": result.meta.latency_ms,
                        }
                    )
                    if self.tool_logger:
                        await self.tool_logger(name, result, started_at, utc_now())
                    if breaker:
                        if result.status in {
                            ToolStatus.TIMEOUT,
                            ToolStatus.FAILED,
                            ToolStatus.DEGRADED,
                        }:
                            breaker.record_failure()
                        else:
                            breaker.record_success()
                    TOOL_CALLS.labels(tool=name, status=result.status).inc()
                    TOOL_DURATION.labels(tool=name, status=result.status).observe(
                        monotonic() - started
                    )
                    return result
                except (TimeoutError, ConnectionError) as exc:
                    if attempt == DEFAULT_MAX_ATTEMPTS:
                        status = (
                            ToolStatus.TIMEOUT
                            if isinstance(exc, TimeoutError)
                            else ToolStatus.DEGRADED
                        )
                        failure = self._failure(trace_id, "TOOL_TIMEOUT", status, attempts=attempt)
                        failure.meta.latency_ms = int((monotonic() - started) * 1000)
                        if self.tool_logger:
                            await self.tool_logger(name, failure, started_at, utc_now())
                        if breaker:
                            breaker.record_failure()
                        TOOL_CALLS.labels(tool=name, status=failure.status).inc()
                        TOOL_DURATION.labels(tool=name, status=failure.status).observe(
                            monotonic() - started
                        )
                        return failure
                except Exception:
                    failure = self._failure(trace_id, "TOOL_PROVIDER_FAILED", ToolStatus.FAILED)
                    failure.meta.latency_ms = int((monotonic() - started) * 1000)
                    if self.tool_logger:
                        await self.tool_logger(name, failure, started_at, utc_now())
                    if breaker:
                        breaker.record_failure()
                    TOOL_CALLS.labels(tool=name, status=failure.status).inc()
                    TOOL_DURATION.labels(tool=name, status=failure.status).observe(
                        monotonic() - started
                    )
                    return failure
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
