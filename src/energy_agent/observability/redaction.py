import hashlib
from enum import StrEnum
from typing import Any


class ContentMode(StrEnum):
    NONE = "none"
    METADATA_ONLY = "metadata_only"
    TRUNCATED = "truncated"


SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "cookie",
        "set-cookie",
        "mysql_dsn",
        "redis_url",
        "langfuse_secret_key",
        "openai_api_key",
        "dashscope_api_key",
        "siliconflow_api_key",
    }
)
CONTENT_KEYS = frozenset(
    {
        "work_order",
        "work_order_body",
        "user_input",
        "user_message",
        "document_chunk",
        "raw_timeseries",
        "timeseries",
    }
)


def _metadata(value: object) -> dict[str, object]:
    serialized = repr(value).encode("utf-8")
    size = len(value) if hasattr(value, "__len__") else None
    return {
        "redacted": True,
        "type": type(value).__name__,
        "count": size,
        "sha256": hashlib.sha256(serialized).hexdigest()[:16],
    }


def redact(
    value: Any,
    *,
    mode: ContentMode | str = ContentMode.METADATA_ONLY,
    max_string_length: int = 512,
    max_list_items: int = 20,
    max_depth: int = 5,
    _depth: int = 0,
) -> Any:
    selected_mode = ContentMode(mode)
    if _depth >= max_depth:
        return {"truncated": True, "reason": "max_depth"}
    if isinstance(value, dict):
        output: dict[str, object] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            normalized = key.lower().replace("-", "_")
            if normalized in {item.replace("-", "_") for item in SENSITIVE_KEYS}:
                output[key] = "[REDACTED]"
            elif normalized in CONTENT_KEYS:
                if selected_mode == ContentMode.NONE:
                    output[key] = None
                elif selected_mode == ContentMode.METADATA_ONLY:
                    output[key] = _metadata(item)
                else:
                    output[key] = redact(
                        item,
                        mode=selected_mode,
                        max_string_length=max_string_length,
                        max_list_items=max_list_items,
                        max_depth=max_depth,
                        _depth=_depth + 1,
                    )
            else:
                output[key] = redact(
                    item,
                    mode=selected_mode,
                    max_string_length=max_string_length,
                    max_list_items=max_list_items,
                    max_depth=max_depth,
                    _depth=_depth + 1,
                )
        return output
    if isinstance(value, (list, tuple)):
        items = [
            redact(
                item,
                mode=selected_mode,
                max_string_length=max_string_length,
                max_list_items=max_list_items,
                max_depth=max_depth,
                _depth=_depth + 1,
            )
            for item in value[:max_list_items]
        ]
        if len(value) > max_list_items:
            items.append({"truncated": True, "omitted_items": len(value) - max_list_items})
        return items
    if isinstance(value, str) and len(value) > max_string_length:
        return value[:max_string_length] + f"…[truncated:{len(value) - max_string_length}]"
    return value


def safe_snapshot(value: object, *, max_bytes: int = 16_384) -> dict[str, object]:
    original_bytes = len(repr(value).encode("utf-8"))
    cleaned = redact(value)
    encoded = repr(cleaned).encode("utf-8")
    if original_bytes <= max_bytes and len(encoded) <= max_bytes:
        return {"data": cleaned, "truncated": False}
    return {
        "data": _metadata(cleaned),
        "truncated": True,
        "original_bytes": original_bytes,
        "limit_bytes": max_bytes,
    }
