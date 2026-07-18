import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from energy_agent.contracts.errors import ErrorBody, ErrorEnvelope
from energy_agent.core.context import get_context
from energy_agent.core.errors import DomainError, ResourceNotFoundError
from energy_agent.core.ids import new_id
from energy_agent.observability.logging import log_event

logger = logging.getLogger(__name__)


def _trace_id() -> str:
    context = get_context()
    return context.trace_id if context else new_id()


def error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    retryable: bool = False,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        ),
        trace_id=_trace_id(),
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        log_event(logger, logging.WARNING, "domain_error", error_code=exc.code)
        status = 404 if isinstance(exc, ResourceNotFoundError) else 503 if exc.retryable else 400
        return error_response(
            code=exc.code,
            message=exc.safe_message,
            status_code=status,
            retryable=exc.retryable,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def handle_unknown_error(request: Request, exc: Exception) -> JSONResponse:
        log_event(
            logger,
            logging.ERROR,
            "unhandled_exception",
            error_code=type(exc).__name__,
        )
        return error_response(
            code="INTERNAL_ERROR",
            message="Internal server error",
            status_code=500,
        )
