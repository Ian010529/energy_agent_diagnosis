import logging
from time import monotonic

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint

from energy_agent.api.errors import install_error_handlers
from energy_agent.api.health import router as health_router
from energy_agent.core.config import Settings, get_settings
from energy_agent.core.context import RequestContext, bind_context, reset_context
from energy_agent.core.ids import trusted_or_new_id
from energy_agent.core.lifecycle import build_lifespan
from energy_agent.observability.logging import log_event

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    selected_settings = settings or get_settings()
    app = FastAPI(
        title=selected_settings.app_name,
        lifespan=build_lifespan(selected_settings),
    )

    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        trace_id = trusted_or_new_id(request.headers.get("X-Trace-ID"))
        request_id = trusted_or_new_id(request.headers.get("X-Request-ID"))
        token = bind_context(RequestContext(trace_id=trace_id, request_id=request_id))
        started = monotonic()
        try:
            with request.app.state.tracer.start_trace(
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
    return app


app = create_app()
