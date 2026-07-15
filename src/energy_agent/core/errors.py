"""Pure HTTP error classification; API handlers belong to later modules."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HTTPErrorPolicy:
    semantic: str
    retryable: bool


HTTP_ERROR_POLICIES: dict[int, HTTPErrorPolicy] = {
    401: HTTPErrorPolicy("authentication", False),
    403: HTTPErrorPolicy("authorization_or_scope", False),
    404: HTTPErrorPolicy("not_found", False),
    409: HTTPErrorPolicy("concurrency_or_idempotency_conflict", False),
    422: HTTPErrorPolicy("validation", False),
    429: HTTPErrorPolicy("rate_limited", True),
    500: HTTPErrorPolicy("unclassified_internal_error", False),
    503: HTTPErrorPolicy("dependency_unavailable", True),
    504: HTTPErrorPolicy("timeout", True),
}


def error_policy(status_code: int) -> HTTPErrorPolicy:
    try:
        return HTTP_ERROR_POLICIES[status_code]
    except KeyError as error:
        raise ValueError(f"unsupported HTTP error status: {status_code}") from error
