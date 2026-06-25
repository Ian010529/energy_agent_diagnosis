"""定义应用异常并安装统一 FastAPI 错误处理器。"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from energy_agent_diagnosis.contracts import ErrorResponse
from energy_agent_diagnosis.core.trace import get_trace_id


class AppError(Exception):
    """表示可以安全暴露给调用方的预期应用错误。"""

    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """保存 HTTP 状态、稳定错误码和可选安全详情。"""
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details


def _error_content(
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
    *,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """生成包含当前 Trace ID 的标准错误内容。"""
    return ErrorResponse(
        error_code=error_code,
        error_message=message,
        trace_id=trace_id if trace_id is not None else get_trace_id(),
        details=details,
    ).model_dump(exclude_none=True)


def install_exception_handlers(app: FastAPI) -> None:
    """为预期异常、校验异常和未知异常注册统一处理器。"""

    def error_response(
        request: Request,
        *,
        status_code: int,
        error_code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> JSONResponse:
        """生成体和响应头使用同一个 Trace 的标准错误响应。"""
        trace_id = str(getattr(request.state, "trace_id", get_trace_id()))
        return JSONResponse(
            status_code=status_code,
            content=_error_content(error_code, message, details, trace_id=trace_id),
            headers={"X-Trace-ID": trace_id} if trace_id else None,
        )

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        """把已知应用异常转换为稳定且可追踪的响应。"""
        return error_response(
            request,
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """把 404、405 等框架异常也转换为稳定错误结构。"""
        codes = {404: "ROUTE_NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
        messages = {404: "请求路径不存在", 405: "请求方法不允许"}
        return error_response(
            request,
            status_code=exc.status_code,
            error_code=codes.get(exc.status_code, "HTTP_ERROR"),
            message=messages.get(exc.status_code, "HTTP 请求失败"),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """隐藏难以稳定消费的框架错误结构，只返回必要校验信息。"""
        # 不回显 input/ctx，既避免 ValueError 无法序列化，也避免把凭据复制到响应。
        safe_errors = [
            {"type": item["type"], "loc": list(item["loc"]), "msg": item["msg"]}
            for item in exc.errors()
        ]
        return error_response(
            request,
            status_code=422,
            error_code="REQUEST_VALIDATION_FAILED",
            message="请求参数校验失败",
            details={"errors": safe_errors},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """记录未知异常但不向调用方泄漏内部实现。"""
        trace_id = str(getattr(request.state, "trace_id", get_trace_id()))
        # 未知异常消息可能夹带凭据，只记录类型和 Trace，不序列化异常文本。
        structlog.get_logger().error(
            "unhandled_exception",
            error_type=type(exc).__name__,
            trace_id=trace_id,
        )
        return error_response(
            request,
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="服务内部错误",
        )
