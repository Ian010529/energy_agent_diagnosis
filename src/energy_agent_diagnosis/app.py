"""组装模块化单服务 FastAPI 应用。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from energy_agent_diagnosis.agent import DiagnosisAgentService
from energy_agent_diagnosis.agent import build_module as build_agent_module
from energy_agent_diagnosis.api.middleware import MetricsMiddleware, TraceMiddleware
from energy_agent_diagnosis.api.routers import (
    build_metrics_router,
    diagnosis_router,
    health_router,
    system_router,
)
from energy_agent_diagnosis.core.config import Settings, get_settings
from energy_agent_diagnosis.core.errors import install_exception_handlers
from energy_agent_diagnosis.core.logging import configure_logging
from energy_agent_diagnosis.core.metrics import Metrics
from energy_agent_diagnosis.core.module import LogicalModule
from energy_agent_diagnosis.infrastructure import ApiKeyAuthAdapter, HealthService
from energy_agent_diagnosis.memory import InMemoryDiagnosisSessionStore
from energy_agent_diagnosis.memory import build_module as build_memory_module
from energy_agent_diagnosis.providers import build_provider_registry
from energy_agent_diagnosis.retrieval import build_module as build_retrieval_module
from energy_agent_diagnosis.tools import build_module as build_tools_module


def _build_modules() -> list[LogicalModule]:
    """创建可独立初始化、未来可迁移到独立进程的逻辑模块。"""
    return [
        build_agent_module(),
        build_retrieval_module(),
        build_tools_module(),
        build_memory_module(),
    ]


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建完整阶段 1 应用，允许测试注入隔离配置。"""
    resolved = settings or get_settings()
    configure_logging(resolved.logging, environment=resolved.app.environment)
    metrics = Metrics(resolved.metrics.namespace)
    modules = _build_modules()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """按顺序初始化模块，并保证逆序释放已初始化资源。"""
        for module in modules:
            await module.initialize()
        app.state.modules = modules
        try:
            yield
        finally:
            for module in reversed(modules):
                await module.shutdown()

    app = FastAPI(
        title=resolved.app.name,
        version=resolved.app.version,
        debug=resolved.app.debug,
        docs_url="/docs" if resolved.app.openapi_enabled else None,
        redoc_url="/redoc" if resolved.app.openapi_enabled else None,
        openapi_url="/openapi.json" if resolved.app.openapi_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.metrics = metrics
    app.state.auth_port = ApiKeyAuthAdapter(resolved.auth)
    app.state.provider_registry = build_provider_registry(resolved.providers)
    app.state.diagnosis_store = InMemoryDiagnosisSessionStore()
    app.state.agent_service = DiagnosisAgentService(
        registry=app.state.provider_registry,
        settings=resolved,
        store=app.state.diagnosis_store,
    )
    app.state.health_service = HealthService(
        resolved.dependencies,
        timeout_seconds=resolved.health.probe_timeout_seconds,
        metrics=metrics,
    )

    app.add_middleware(MetricsMiddleware, metrics=metrics)
    app.add_middleware(TraceMiddleware)
    install_exception_handlers(app)
    app.include_router(health_router)
    if resolved.metrics.enabled:
        app.include_router(build_metrics_router(resolved.metrics.path))
    app.include_router(system_router)
    app.include_router(diagnosis_router)
    return app
