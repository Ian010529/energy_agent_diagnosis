from __future__ import annotations

from typing import Any

import pytest
from pytest import MonkeyPatch

from scripts.m0_gate import M0Probe, validate_gate_counts


class FakeChannel:
    def __init__(self) -> None:
        self.confirm_enabled = False
        self.published = False

    def confirm_delivery(self) -> None:
        self.confirm_enabled = True

    def queue_declare(self, **_: Any) -> None:
        return None

    def basic_publish(self, **_: Any) -> None:
        self.published = True
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.channel_instance = FakeChannel()
        self.closed = False

    def channel(self) -> FakeChannel:
        return self.channel_instance

    def close(self) -> None:
        self.closed = True


def test_pika_none_return_is_a_confirmed_publish(monkeypatch: MonkeyPatch) -> None:
    probe = M0Probe(
        {"RABBITMQ_DEFAULT_USER": "user", "RABBITMQ_DEFAULT_PASS": "password"},
        "019f6225-98e1-7d7f-b238-774a777a41fd",
    )
    connection = FakeConnection()
    monkeypatch.setattr(probe, "rabbit", lambda: connection)

    probe._write_rabbitmq()

    assert connection.channel_instance.confirm_enabled
    assert connection.channel_instance.published
    assert connection.closed


def test_gate_counts_reject_skips() -> None:
    with pytest.raises(RuntimeError, match="skipped=1"):
        validate_gate_counts({"tests": 18, "failures": 0, "errors": 0, "skipped": 1})

    validate_gate_counts({"tests": 18, "failures": 0, "errors": 0, "skipped": 0})
