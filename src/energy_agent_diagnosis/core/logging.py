"""配置不会泄漏敏感配置的结构化日志。"""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any, cast

import structlog

from energy_agent_diagnosis.core.config import LoggingSettings

_SENSITIVE_KEYS = {"api_key", "authorization", "password", "secret", "token"}


def _redact_value(value: Any) -> Any:
    """递归复制容器并遮蔽任意层级的敏感键。"""
    if isinstance(value, MutableMapping):
        return {
            key: "***"
            if any(part in str(key).lower() for part in _SENSITIVE_KEYS)
            else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    return value


def _redact_sensitive_fields(
    _logger: Any,
    _method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """在日志渲染前遮蔽常见敏感字段值，避免配置误打到控制台。"""
    return cast(MutableMapping[str, Any], _redact_value(event_dict))


def configure_logging(settings: LoggingSettings, *, environment: str) -> None:
    """根据环境选择 JSON 或可读控制台日志。"""
    level = getattr(logging, settings.level.upper(), logging.INFO)
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s", force=True)
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.uses_json(environment)
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            # 异常格式化可能新增嵌套字段，因此脱敏必须作为最后一个渲染前处理器。
            _redact_sensitive_fields,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
