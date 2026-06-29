"""验证阶段 2 Mock 数据资产的规模、字段和跨文件一致性。"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

FIXTURE_ROOT = Path(__file__).parents[1] / "src" / "energy_agent_diagnosis" / "fixtures"


def load_fixture(relative_path: str) -> list[dict[str, Any]]:
    """读取 fixture 并确认其为对象数组。"""
    raw: object = json.loads((FIXTURE_ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(raw, list)
    assert all(isinstance(item, dict) for item in raw)
    return raw


def assert_timezone(value: object) -> None:
    """确认时间字符串带时区，避免阶段 2 数据混入本地时间。"""
    assert isinstance(value, str)
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None


def test_fixture_sizes_meet_stage2_mock_baseline() -> None:
    """Mock 数据规模达到文档建议的最小演示基线。"""
    assert 10 <= len(load_fixture("devices.json")) <= 20
    assert 20 <= len(load_fixture("alarms.json")) <= 50
    assert len(load_fixture("timeseries/summaries.json")) >= 20
    assert 100 <= len(load_fixture("manuals/chunks.json")) <= 300
    assert 30 <= len(load_fixture("tickets.json")) <= 100
    assert 20 <= len(load_fixture("graph_relations.json")) <= 50


def test_device_fixtures_have_required_stage2_fields() -> None:
    """设备画像 fixture 覆盖阶段 2 必填字段。"""
    required = {
        "device_id",
        "device_type",
        "device_model",
        "manufacturer",
        "site_id",
        "commission_time",
        "status",
    }
    for device in load_fixture("devices.json"):
        assert required <= device.keys()
        assert_timezone(device["commission_time"])


def test_alarm_fixtures_have_timezone_trigger_time_and_known_device() -> None:
    """告警 fixture 必须关联已知设备并保留带时区触发时间。"""
    devices = {item["device_id"] for item in load_fixture("devices.json")}
    required = {"alarm_id", "device_id", "site_id", "alarm_name", "alarm_level", "trigger_time"}
    for alarm in load_fixture("alarms.json"):
        assert required <= alarm.keys()
        assert alarm["device_id"] in devices
        assert_timezone(alarm["trigger_time"])


def test_timeseries_fixtures_have_required_metrics_and_quality_fields() -> None:
    """时序 fixture 返回摘要，不把大量原始点塞进 Agent。"""
    alarms = {item["alarm_id"] for item in load_fixture("alarms.json")}
    for summary in load_fixture("timeseries/summaries.json"):
        assert {"device_id", "alarm_id", "start_time", "end_time", "metrics"} <= summary.keys()
        assert summary["alarm_id"] in alarms
        assert_timezone(summary["start_time"])
        assert_timezone(summary["end_time"])
        assert isinstance(summary["metrics"], list)
        assert summary["metrics"]
        for metric in summary["metrics"]:
            assert {
                "metric_name",
                "min",
                "max",
                "avg",
                "trend",
                "quality",
                "anomaly_points",
            } <= metric.keys()


def test_manual_chunks_have_required_metadata_and_keywords() -> None:
    """手册 chunk fixture 必须具备可检索 metadata。"""
    required = {
        "doc_id",
        "chunk_id",
        "content",
        "device_type",
        "device_model",
        "manufacturer",
        "chapter_title",
        "section_type",
        "page_no",
        "version",
        "keywords",
    }
    for chunk in load_fixture("manuals/chunks.json"):
        assert required <= chunk.keys()
        assert isinstance(chunk["keywords"], list)
        assert chunk["keywords"]


def test_ticket_fixtures_have_cleaned_case_fields_and_verified_flags() -> None:
    """工单 fixture 必须区分已审核强证据和弱参考。"""
    tickets = load_fixture("tickets.json")
    required = {
        "ticket_id",
        "site_id",
        "device_id",
        "device_model",
        "alarm_name",
        "fault_symptom",
        "root_cause",
        "action_taken",
        "is_verified",
        "close_time",
    }
    assert any(item["is_verified"] is True for item in tickets)
    assert any(item["is_verified"] is False for item in tickets)
    for ticket in tickets:
        assert required <= ticket.keys()
        assert isinstance(ticket["is_verified"], bool)
        assert_timezone(ticket["close_time"])


def test_graph_relations_have_required_stage2_fields() -> None:
    """图谱关系 fixture 覆盖告警、部件、根因和动作。"""
    alarm_names = {item["alarm_name"] for item in load_fixture("alarms.json")}
    required = {
        "relation_id",
        "alarm_name",
        "device_type",
        "component",
        "fault_cause",
        "action",
        "confidence",
        "source_refs",
        "verified",
    }
    for relation in load_fixture("graph_relations.json"):
        assert required <= relation.keys()
        assert relation["alarm_name"] in alarm_names
        assert 0 <= relation["confidence"] <= 1
        assert isinstance(relation["source_refs"], list)
