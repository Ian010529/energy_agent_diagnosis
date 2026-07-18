import asyncio
import logging
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
)
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from energy_agent.core.config import Settings
from energy_agent.memory.session_store import RedisSessionStore
from energy_agent.observability.langfuse import LangFuseTracer
from energy_agent.observability.logging import configure_logging, log_event
from energy_agent.observability.tracing import LocalTracer, Tracer
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.persistence.redis import create_redis_client
from energy_agent.persistence.repositories.diagnosis_session import (
    DiagnosisSessionRepository,
)
from energy_agent.persistence.repositories.diagnosis_step_log import (
    DiagnosisStepLogRepository,
)

logger = logging.getLogger(__name__)


def create_tracer(settings: Settings) -> Tracer:
    if settings.observability_mode == "langfuse":
        assert settings.langfuse_public_key is not None
        assert settings.langfuse_secret_key is not None
        return LangFuseTracer(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            environment=settings.app_env,
            mode=settings.trace_content_mode,
        )
    return LocalTracer(settings.trace_content_mode)


async def _close(name: str, operation: Awaitable[object]) -> None:
    try:
        async with asyncio.timeout(5.0):
            await operation
    except Exception:
        log_event(logger, logging.ERROR, "resource_close_failed", error_code=name)


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.log_format)
        tracer = create_tracer(settings)
        engine = create_mysql_engine(settings.mysql_dsn)
        session_factory = create_session_factory(engine)
        redis = create_redis_client(settings.redis_url)

        app.state.settings = settings
        app.state.tracer = tracer
        app.state.mysql_engine = engine
        app.state.redis = redis
        app.state.session_repository = DiagnosisSessionRepository(session_factory, tracer)
        app.state.step_log_repository = DiagnosisStepLogRepository(session_factory, tracer)
        app.state.session_store = RedisSessionStore(
            redis, settings.redis_session_ttl_seconds, tracer
        )
        log_event(logger, logging.INFO, "application_started")
        try:
            yield
        finally:
            await _close("tracer_flush", tracer.flush())
            await _close("tracer_shutdown", tracer.shutdown())
            await _close("redis", redis.aclose())
            await _close("mysql", engine.dispose())
            log_event(logger, logging.INFO, "application_stopped")

    return lifespan
