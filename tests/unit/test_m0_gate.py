from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from scripts.m0_gate import M0Probe, run_gate, validate_gate_counts, write_combined_junit


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


def test_readback_rejects_unregistered_service() -> None:
    probe = M0Probe({}, "019f6225-98e1-7d7f-b238-774a777a41fd")

    with pytest.raises(RuntimeError, match="no authoritative readback"):
        probe.readback(("unregistered",))


def test_dirty_gate_is_blocked_before_commit_is_recorded(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    run_id = "019f639e-263c-74ea-ac17-a1c74b5d1957"

    def dirty_status(arguments: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        assert arguments[:3] != ["git", "rev-parse", "HEAD"]
        return subprocess.CompletedProcess(arguments, 0, stdout=" M tracked.py\n")

    monkeypatch.setattr("scripts.m0_gate.ROOT", tmp_path)
    monkeypatch.setattr("scripts.m0_gate.uuid7", lambda: run_id)
    monkeypatch.setattr("scripts.m0_gate.command", dirty_status)

    with pytest.raises(RuntimeError, match="clean source tree"):
        run_gate()

    evidence = json.loads(
        (tmp_path / "artifacts/gates/M0" / run_id / "gate.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["result"] == "BLOCKED"
    assert evidence["commit_sha"] == "NOT_RECORDED"
    assert evidence["failed_step"] == "verify clean source tree"


def test_combined_junit_contains_all_suites(tmp_path: Path) -> None:
    unit = tmp_path / "unit.xml"
    contract = tmp_path / "contract.xml"
    unit.write_text('<testsuite name="unit" tests="1"/>', encoding="utf-8")
    contract.write_text(
        '<testsuites><testsuite name="contract" tests="2"/></testsuites>',
        encoding="utf-8",
    )
    combined = tmp_path / "junit.xml"

    write_combined_junit([unit, contract], combined)

    names = [suite.attrib["name"] for suite in ET.parse(combined).getroot()]
    assert names == ["unit", "contract"]
