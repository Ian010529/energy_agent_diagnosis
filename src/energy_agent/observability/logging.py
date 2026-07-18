import json
import logging
from datetime import UTC, datetime
from typing import Any

from energy_agent.core.context import context_fields
from energy_agent.observability.redaction import redact


class ContextFormatter(logging.Formatter):
    def __init__(self, *, json_output: bool) -> None:
        super().__init__()
        self.json_output = json_output

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
            "logger": record.name,
            **context_fields(),
        }
        for field in (
            "trace_id",
            "request_id",
            "session_id",
            "run_id",
            "duration_ms",
            "error_code",
            "status_code",
            "span_name",
            "span_status",
            "metadata",
        ):
            value = getattr(record, field, None)
            if value is not None and payload.get(field) is None:
                payload[field] = value
        payload = redact(payload)
        if self.json_output:
            return json.dumps(payload, ensure_ascii=False, default=str)
        context = " ".join(
            f"{key}={value}"
            for key, value in payload.items()
            if key not in {"timestamp", "level", "event", "logger"} and value is not None
        )
        return (
            f"{payload['timestamp']} {payload['level']} {payload['logger']} "
            f"{payload['event']}{' ' + context if context else ''}"
        )


def configure_logging(level: str, log_format: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(ContextFormatter(json_output=log_format == "json"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    **fields: object,
) -> None:
    logger.log(level, event, extra={"event": event, **fields})
