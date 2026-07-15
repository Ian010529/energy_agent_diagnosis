"""The project's only canonicalization implementation (version 2)."""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from json.encoder import encode_basestring
from typing import Any, Final
from uuid import UUID

from pydantic import BaseModel

CANONICALIZATION_VERSION: Final = 2


class CanonicalizationError(ValueError):
    """Input cannot be represented by canonicalization v2."""


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise CanonicalizationError("NaN and Infinity are forbidden")
    if value.is_zero():
        return "0"
    try:
        text = format(value, "f")
    except InvalidOperation as error:
        raise CanonicalizationError("invalid decimal") from error
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CanonicalizationError("datetime must include a timezone")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return encode_basestring(unicodedata.normalize("NFC", value))
    if isinstance(value, datetime):
        return encode_basestring(_datetime_text(value))
    if isinstance(value, UUID):
        return encode_basestring(str(value))
    if isinstance(value, Enum):
        return _encode(value.value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError("NaN and Infinity are forbidden")
        return _decimal_text(Decimal(str(value)))
    if isinstance(value, BaseModel):
        return _encode(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise CanonicalizationError("object keys collide after NFC normalization")
            normalized[normalized_key] = item
        entries = (
            f"{encode_basestring(key)}:{_encode(normalized[key])}"
            for key in sorted(normalized)
        )
        return "{" + ",".join(entries) + "}"
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    raise CanonicalizationError(f"unsupported canonicalization type: {type(value).__name__}")


def canonicalize(value: Any) -> bytes:
    """Return canonical UTF-8 JSON bytes for a supported value."""

    return _encode(value).encode("utf-8")


def canonical_digest(value: Any) -> str:
    """Return the lowercase SHA-256 digest of canonical bytes."""

    return hashlib.sha256(canonicalize(value)).hexdigest()
