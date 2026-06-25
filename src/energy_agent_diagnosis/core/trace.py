"""在请求、日志和错误响应之间安全传递 Trace ID。"""

import re
from contextvars import ContextVar, Token
from uuid import uuid4

_TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def normalize_trace_id(value: str | None) -> str:
    """接受安全的调用方 Trace ID，否则生成新的不可预测标识。"""
    if value and _TRACE_ID_PATTERN.fullmatch(value):
        return value
    return uuid4().hex


def set_trace_id(value: str) -> Token[str]:
    """为当前异步上下文设置 Trace ID，并返回可复位的令牌。"""
    return _trace_id.set(value)


def reset_trace_id(token: Token[str]) -> None:
    """恢复进入当前上下文前的 Trace ID。"""
    _trace_id.reset(token)


def get_trace_id() -> str:
    """返回当前请求的 Trace ID；请求外可能为空字符串。"""
    return _trace_id.get()
