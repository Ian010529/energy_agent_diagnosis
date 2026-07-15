from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import pytest
import redis

ROOT = Path(__file__).resolve().parents[2]


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.fail(f"{name} is required for the M1 live Redis test")
    return value


def snapshot(client: Any, keys: list[str]) -> list[tuple[str, bytes | None]]:
    return [(cast(bytes, client.type(key)).decode(), client.dump(key)) for key in keys]


def test_real_redis_type_error_has_zero_partial_writes() -> None:
    client = redis.Redis(
        host=required("M1_REDIS_HOST"),
        port=int(required("M1_REDIS_PORT")),
        password=required("REDIS_PASSWORD"),
        decode_responses=False,
    )
    prefix = required("M1_REDIS_TEST_PREFIX")
    keys = [f"{prefix}:session", f"{prefix}:run", f"{prefix}:pending", f"{prefix}:audit"]
    client.delete(*keys)
    client.set(keys[-1], b"wrong-type")
    before = snapshot(client, keys)
    result = client.eval(
        (ROOT / "scripts/migrations/atomic_preflight.lua").read_text(encoding="utf-8"),
        len(keys),
        *keys,
        "1",
        "run-live-test",
        "b" * 64,
        "0",
    )
    assert result[:2] == [0, b"KEY_TYPE_MISMATCH"]
    assert snapshot(client, keys) == before
    client.delete(*keys)
