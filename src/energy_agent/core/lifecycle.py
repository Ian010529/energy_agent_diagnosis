import asyncio
import logging
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
)
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from influxdb_client.client.influxdb_client import InfluxDBClient

from energy_agent.core.config import Settings
from energy_agent.memory.session_store import RedisSessionStore
from energy_agent.model.gateway import ModelGateway
from energy_agent.observability.langfuse import LangFuseTracer
from energy_agent.observability.logging import configure_logging, log_event
from energy_agent.observability.tracing import LocalTracer, Tracer
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.persistence.redis import create_redis_client
from energy_agent.persistence.repositories.diagnosis_run import (
    DiagnosisResultRepository,
    DiagnosisRunRepository,
)
from energy_agent.persistence.repositories.diagnosis_session import (
    DiagnosisSessionRepository,
)
from energy_agent.persistence.repositories.diagnosis_step_log import (
    DiagnosisStepLogRepository,
)
from energy_agent.providers.influxdb import InfluxTimeseriesProvider
from energy_agent.providers.mysql import MySQLDiagnosisProvider
from energy_agent.tools.implementations.read_tools import build_registry

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
        influx_client = InfluxDBClient(
            url=settings.influxdb_url,
            token=settings.influxdb_token,
            org=settings.influxdb_org,
            timeout=int(settings.influxdb_query_timeout_seconds * 1000),
        )
        mysql_provider = MySQLDiagnosisProvider(session_factory)
        timeseries_provider = InfluxTimeseriesProvider(
            influx_client,
            settings.influxdb_org,
            settings.influxdb_bucket,
            settings.influxdb_query_timeout_seconds,
        )
        model_gateway = (
            ModelGateway(
                base_url=settings.model_gateway_base_url,
                api_key=settings.model_gateway_api_key,
                model=settings.model_name,
                timeout_seconds=settings.model_timeout_seconds,
                temperature=settings.model_temperature,
                tracer=tracer,
            )
            if settings.model_mode == "openai_compatible"
            and settings.model_gateway_base_url
            and settings.model_gateway_api_key
            else None
        )

        app.state.settings = settings
        app.state.tracer = tracer
        app.state.mysql_engine = engine
        app.state.redis = redis
        app.state.influx_client = influx_client
        app.state.session_repository = DiagnosisSessionRepository(session_factory, tracer)
        app.state.step_log_repository = DiagnosisStepLogRepository(session_factory, tracer)
        app.state.run_repository = DiagnosisRunRepository(session_factory, tracer)
        app.state.result_repository = DiagnosisResultRepository(session_factory, tracer)
        app.state.mysql_provider = mysql_provider
        app.state.timeseries_provider = timeseries_provider
        app.state.tool_registry = build_registry(mysql_provider, timeseries_provider, tracer)
        app.state.model_gateway = model_gateway
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
            await _close("influxdb", asyncio.to_thread(influx_client.close))
            await _close("mysql", engine.dispose())
            log_event(logger, logging.INFO, "application_stopped")

    return lifespan
