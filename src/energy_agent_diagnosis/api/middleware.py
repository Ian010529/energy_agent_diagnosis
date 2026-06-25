"""实现 Trace 和低基数 HTTP 指标中间件。"""

from collections.abc import Awaitable, Callable
from time import perf_counter

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from energy_agent_diagnosis.core.metrics import Metrics
from energy_agent_diagnosis.core.trace import normalize_trace_id, reset_trace_id, set_trace_id

RequestHandler = Callable[[Request], Awaitable[Response]]


def _route_label(request: Request) -> str:
    """在路由匹配后读取模板路径，避免把原始 URL 放入指标标签。"""
    route_object = request.scope.get("route")
    return str(getattr(route_object, "path", "unmatched"))


class MetricsMiddleware(BaseHTTPMiddleware):
    """记录请求量、耗时和异常，不使用原始 URL 等高基数标签。"""

    def __init__(self, app: ASGIApp, metrics: Metrics) -> None:
        """绑定应用实例独立的指标注册表。"""
        super().__init__(app)
        self._metrics = metrics

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        """记录路由模板级指标，并让异常继续进入统一处理器。"""
        started = perf_counter()
        try:
            response = await call_next(request)
            route = _route_label(request)
            self._metrics.request_count.labels(
                request.method,
                route,
                str(response.status_code),
            ).inc()
            return response
        except Exception as exc:
            route = _route_label(request)
            self._metrics.exception_count.labels(
                request.method,
                route,
                type(exc).__name__,
            ).inc()
            self._metrics.request_count.labels(request.method, route, "500").inc()
            raise
        finally:
            route = _route_label(request)
            self._metrics.request_duration.labels(request.method, route).observe(
                perf_counter() - started
            )


class TraceMiddleware(BaseHTTPMiddleware):
    """为每个请求建立独立 Trace 上下文并返回响应头。"""

    async def dispatch(self, request: Request, call_next: RequestHandler) -> Response:
        """验证调用方 Trace，防止任意内容进入日志上下文。"""
        trace_id = normalize_trace_id(request.headers.get("X-Trace-ID"))
        # request.state 跨越 Starlette 的外层异常处理边界，ContextVar 清理后仍可追溯 500。
        request.state.trace_id = trace_id
        token = set_trace_id(trace_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        try:
            response = await call_next(request)
            response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
            reset_trace_id(token)
