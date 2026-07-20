import asyncio
import hashlib
import logging
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any, Literal, Self

from energy_agent.observability.logging import log_event
from energy_agent.observability.redaction import ContentMode, redact

logger = logging.getLogger(__name__)


class LangFuseSpan(AbstractContextManager["LangFuseSpan"]):
    def __init__(
        self,
        manager: AbstractContextManager[Any],
        mode: ContentMode,
        on_failure: Callable[[], None],
    ) -> None:
        self.manager = manager
        self.mode = mode
        self.on_failure = on_failure
        self.observation: Any = None
        self.error_recorded = False

    def __enter__(self) -> Self:
        try:
            self.observation = self.manager.__enter__()
        except Exception:
            self.on_failure()
            log_event(logger, logging.ERROR, "trace_export_failed")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if exc_value is not None and not self.error_recorded:
            self.record_error(exc_value)
        if self.observation is None:
            return False
        try:
            self.manager.__exit__(exc_type, exc_value, traceback)
        except Exception:
            self.on_failure()
            log_event(logger, logging.ERROR, "trace_export_failed")
        return False

    def set_output(self, output: object) -> None:
        if self.observation is None:
            return
        try:
            self.observation.update(output=redact(output, mode=self.mode))
        except Exception:
            self.on_failure()
            log_event(logger, logging.ERROR, "trace_export_failed")

    def record_event(self, name: str, metadata: dict[str, object] | None = None) -> None:
        if self.observation is None:
            return
        try:
            self.observation.create_event(
                name=name,
                metadata=redact(metadata or {}, mode=self.mode),
            )
        except Exception:
            self.on_failure()
            log_event(logger, logging.ERROR, "trace_export_failed")

    def record_error(self, error: BaseException) -> None:
        self.error_recorded = True
        if self.observation is None:
            return
        try:
            self.observation.update(
                level="ERROR",
                status_message=type(error).__name__,
            )
        except Exception:
            self.on_failure()
            log_event(logger, logging.ERROR, "trace_export_failed")


class LangFuseTracer:
    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        host: str,
        environment: str,
        mode: ContentMode | str = ContentMode.METADATA_ONLY,
        client: Any | None = None,
        shutdown_timeout_seconds: float = 3.0,
    ) -> None:
        if client is None:
            from langfuse import Langfuse

            client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                base_url=host,
                environment=environment,
            )
        self.client: Any = client
        self.mode = ContentMode(mode)
        self.shutdown_timeout_seconds = shutdown_timeout_seconds
        self.export_failed = False

    def _mark_export_failed(self) -> None:
        self.export_failed = True

    @staticmethod
    def _langfuse_trace_id(trace_id: str) -> str:
        compact = trace_id.replace("-", "").lower()
        if re.fullmatch(r"[0-9a-f]{32}", compact):
            return compact
        return hashlib.sha256(trace_id.encode("utf-8")).hexdigest()[:32]

    def _start(
        self,
        name: str,
        trace_id: str,
        metadata: dict[str, object] | None,
        *,
        as_type: str,
        model: str | None = None,
    ) -> LangFuseSpan:
        kwargs: dict[str, object] = {
            "name": name,
            "as_type": as_type,
            "trace_context": {"trace_id": self._langfuse_trace_id(trace_id)},
            "metadata": redact(metadata or {}, mode=self.mode),
        }
        if model is not None:
            kwargs["model"] = model
        try:
            manager = self.client.start_as_current_observation(**kwargs)
        except Exception:
            self._mark_export_failed()
            log_event(logger, logging.ERROR, "trace_export_failed")
            manager = _NoopManager()
        return LangFuseSpan(manager, self.mode, self._mark_export_failed)

    def start_trace(
        self, name: str, *, trace_id: str, metadata: dict[str, object] | None = None
    ) -> LangFuseSpan:
        return self._start(name, trace_id, metadata, as_type="span")

    def start_span(
        self, name: str, *, trace_id: str, metadata: dict[str, object] | None = None
    ) -> LangFuseSpan:
        return self._start(name, trace_id, metadata, as_type="span")

    def start_generation(
        self,
        name: str,
        *,
        trace_id: str,
        model: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> LangFuseSpan:
        return self._start(name, trace_id, metadata, as_type="generation", model=model)

    async def flush(self) -> None:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self.client.flush),
                timeout=self.shutdown_timeout_seconds,
            )
        except Exception:
            self._mark_export_failed()
            log_event(logger, logging.ERROR, "trace_export_failed")

    async def shutdown(self) -> None:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self.client.shutdown),
                timeout=self.shutdown_timeout_seconds,
            )
        except Exception:
            self._mark_export_failed()
            log_event(logger, logging.ERROR, "trace_export_failed")


class _NoopManager(AbstractContextManager[None]):
    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        return False
