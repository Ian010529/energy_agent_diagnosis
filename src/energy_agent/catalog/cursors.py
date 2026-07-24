import base64
import binascii
from datetime import UTC, datetime

from energy_agent.core.errors import InvalidRequestError


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def decode_cursor(value: str | None) -> str | None:
    if not value:
        return None
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        ).decode()
        if not decoded:
            raise ValueError("empty cursor")
        return decoded
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise InvalidRequestError("Cursor is invalid") from exc


def query_datetime(value: object) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo is not None else parsed
