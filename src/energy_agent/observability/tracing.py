import logging
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Literal, Protocol, Self

from energy_agent.core.time import utc_now
from energy_agent.observability.logging import log_event
from energy_agent.observability.redaction import ContentMode, redact

logger = logging.getLogger(__name__)


class Span(Protocol):
    def set_output(self, output: object) -> None: ...

    def record_event(self, name: str, metadata: dict[str, object] | None = None) -> None: ...

    def record_error(self, error: BaseException) -> None: ...


class SpanContext(AbstractContextManager[Span], Protocol):
    pass


class Tracer(Protocol):
    def start_trace(
        self,
        name: str,
        *,
        trace_id: str,
        metadata: dict[str, object] | None = None,
    ) -> SpanContext: ...

    def start_span(
        self,
        name: str,
        *,
        trace_id: str,
        metadata: dict[str, object] | None = None,
    ) -> SpanContext: ...

    def start_generation(
        self,
        name: str,
        *,
        trace_id: str,
        model: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> SpanContext: ...

    async def flush(self) -> None: ...

    async def shutdown(self) -> None: ...


class LocalSpan(AbstractContextManager[Span]):
    def __init__(
        self,
        name: str,
        trace_id: str,
        metadata: dict[str, object] | None,
        mode: ContentMode,
    ) -> None:
        self.name = name
        self.trace_id = trace_id
        self.metadata = redact(metadata or {}, mode=mode)
        self.mode = mode
        self.started_at = utc_now()
        self.status = "ok"

    def __enter__(self) -> Self:
        log_event(
            logger,
            logging.INFO,
            "trace_span_started",
            trace_id=self.trace_id,
            span_name=self.name,
            span_status="started",
            metadata=self.metadata,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if exc_value is not None and self.status != "error":
            self.record_error(exc_value)
        duration_ms = int((utc_now() - self.started_at).total_seconds() * 1000)
        log_event(
            logger,
            logging.INFO,
            "trace_span_finished",
            trace_id=self.trace_id,
            span_name=self.name,
            span_status=self.status,
            duration_ms=duration_ms,
            error_code=None if self.status == "ok" else "SPAN_ERROR",
        )
        return False

    def set_output(self, output: object) -> None:
        self.output = redact(output, mode=self.mode)

    def record_event(self, name: str, metadata: dict[str, object] | None = None) -> None:
        log_event(
            logger,
            logging.INFO,
            name,
            trace_id=self.trace_id,
            span_name=self.name,
            metadata=redact(metadata or {}, mode=self.mode),
        )

    def record_error(self, error: BaseException) -> None:
        self.status = "error"
        log_event(
            logger,
            logging.ERROR,
            "trace_error",
            trace_id=self.trace_id,
            span_name=self.name,
            span_status=self.status,
            error_code=type(error).__name__,
        )


class LocalTracer:
    def __init__(self, mode: ContentMode | str = ContentMode.METADATA_ONLY) -> None:
        self.mode = ContentMode(mode)

    def _start(self, name: str, trace_id: str, metadata: dict[str, object] | None) -> LocalSpan:
        return LocalSpan(name, trace_id, metadata, self.mode)

    def start_trace(
        self, name: str, *, trace_id: str, metadata: dict[str, object] | None = None
    ) -> LocalSpan:
        return self._start(name, trace_id, metadata)

    def start_span(
        self, name: str, *, trace_id: str, metadata: dict[str, object] | None = None
    ) -> LocalSpan:
        return self._start(name, trace_id, metadata)

    def start_generation(
        self,
        name: str,
        *,
        trace_id: str,
        model: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> LocalSpan:
        combined = {**(metadata or {}), "model": model}
        return self._start(name, trace_id, combined)

    async def flush(self) -> None:
        log_event(logger, logging.INFO, "trace_flush")

    async def shutdown(self) -> None:
        log_event(logger, logging.INFO, "trace_shutdown")


SPAN_NAMES = frozenset(
    {
        "diagnosis.request",
        "diagnosis.workflow",
        "agent.intent_router",
        "agent.entity_parser",
        "agent.plan_builder",
        "agent.tool_dispatcher",
        "agent.evidence_aggregator",
        "agent.gap_detector",
        "agent.reason_generator",
        "agent.response_generator",
        "agent.rule_checker",
        "agent.memory_writer",
        "retrieval.query_rewrite",
        "retrieval.keyword_search",
        "retrieval.vector_search",
        "retrieval.rerank",
        "retrieval.evidence_aggregation",
    }
)
