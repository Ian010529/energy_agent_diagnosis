import logging
from time import monotonic

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware

from energy_agent.api.cases import router as cases_router
from energy_agent.api.catalog import router as catalog_router
from energy_agent.api.diagnosis import router as diagnosis_router
from energy_agent.api.errors import error_response, install_error_handlers
from energy_agent.api.evidence import router as evidence_router
from energy_agent.api.health import router as health_router
from energy_agent.api.metrics import router as metrics_router
from energy_agent.api.session_queries import router as session_queries_router
from energy_agent.bootstrap.lifespan import build_lifespan
from energy_agent.core.config import Settings, get_settings
from energy_agent.core.context import ActorRole, RequestContext, bind_context, reset_context
from energy_agent.core.ids import trusted_or_new_id
from energy_agent.observability.logging import log_event
from energy_agent.observability.metrics import (
    HTTP_DURATION,
    HTTP_REQUESTS,
    RATE_LIMIT_REJECTIONS,
    normalized_route,
)

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    selected_settings = settings or get_settings()
    app = FastAPI(
        title=selected_settings.app_name,
        lifespan=build_lifespan(selected_settings),
    )
    origins = [
        item.strip() for item in selected_settings.cors_allow_origins.split(",") if item.strip()
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=[
                "Content-Type",
                "Idempotency-Key",
                "X-Actor-ID",
                "X-Actor-Role",
                "X-Internal-API-Key",
                "X-Request-ID",
                "X-Trace-ID",
            ],
        )

    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        trace_id = trusted_or_new_id(request.headers.get("X-Trace-ID"))
        request_id = trusted_or_new_id(request.headers.get("X-Request-ID"))
        actor_id = request.headers.get("X-Actor-ID")
        role_value = request.headers.get("X-Actor-Role")
        try:
            actor_role = ActorRole(role_value) if role_value else None
        except ValueError:
            actor_role = None
        if (
            not actor_id
            and selected_settings.auth_mode == "development_headers"
            and selected_settings.app_env in {"local", "test"}
        ):
            actor_id = "local-operator"
            actor_role = ActorRole.OPERATOR
        token = bind_context(
            RequestContext(
                trace_id=trace_id,
                request_id=request_id,
                actor_id=actor_id,
                actor_role=actor_role,
            )
        )
        started = monotonic()
        try:
            if request.method in {"POST", "PUT", "PATCH"}:
                content_length = request.headers.get("content-length")
                if (
                    content_length
                    and content_length.isdigit()
                    and int(content_length) > selected_settings.request_body_max_bytes
                ):
                    return error_response(
                        code="REQUEST_BODY_TOO_LARGE",
                        message="Request body exceeds the configured limit",
                        status_code=413,
                    )
                body = await request.body()
                if len(body) > selected_settings.request_body_max_bytes:
                    return error_response(
                        code="REQUEST_BODY_TOO_LARGE",
                        message="Request body exceeds the configured limit",
                        status_code=413,
                    )
            if selected_settings.rate_limit_enabled and request.method in {
                "POST",
                "PUT",
                "PATCH",
            }:
                path = request.url.path
                group = (
                    "review"
                    if path.endswith("/review")
                    else "case_write"
                    if "/cases/" in path
                    else "diagnosis"
                )
                limit = (
                    selected_settings.rate_limit_review_per_minute
                    if group == "review"
                    else selected_settings.rate_limit_case_write_per_minute
                    if group == "case_write"
                    else selected_settings.rate_limit_diagnosis_per_minute
                )
                rate_actor = actor_id or "local-operator"
                try:
                    allowed, retry_after = await request.app.state.container.rate_limiter.allow(
                        rate_actor, group, limit
                    )
                except Exception:
                    if selected_settings.pilot_mode:
                        return error_response(
                            code="RATE_LIMIT_UNAVAILABLE",
                            message="Pilot writes are closed while rate limiting is unavailable",
                            status_code=503,
                            retryable=True,
                        )
                else:
                    if not allowed:
                        RATE_LIMIT_REJECTIONS.labels(group=group).inc()
                        rejected = error_response(
                            code="RATE_LIMITED",
                            message="Rate limit exceeded",
                            status_code=429,
                            retryable=True,
                        )
                        rejected.headers["Retry-After"] = str(retry_after)
                        return rejected
            with request.app.state.container.tracer.start_trace(
                "diagnosis.request",
                trace_id=trace_id,
                metadata={"method": request.method, "path": request.url.path},
            ) as span:
                try:
                    response = await call_next(request)
                except Exception as exc:
                    span.record_error(exc)
                    raise
                span.set_output({"status_code": response.status_code})
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            route = normalized_route(request.url.path)
            elapsed = monotonic() - started
            HTTP_REQUESTS.labels(
                method=request.method, route=route, status=str(response.status_code)
            ).inc()
            HTTP_DURATION.labels(method=request.method, route=route).observe(elapsed)
            if not request.url.path.startswith("/health/"):
                log_event(
                    logger,
                    logging.INFO,
                    "http_request_completed",
                    status_code=response.status_code,
                    duration_ms=int((monotonic() - started) * 1000),
                )
            return response
        finally:
            reset_context(token)

    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(catalog_router)
    app.include_router(session_queries_router)
    app.include_router(evidence_router)
    app.include_router(diagnosis_router)
    app.include_router(cases_router)
    app.include_router(metrics_router)
    return app


app = create_app()
