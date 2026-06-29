"""图谱关系 Mock Provider，提供阶段 2 关系补充和降级基线。"""

import json
from pathlib import Path
from typing import cast

from energy_agent_diagnosis.contracts import (
    ProviderType,
    ToolContext,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
from energy_agent_diagnosis.ports.providers import Payload, ProviderResult


class MockGraphRelationProvider:
    """从简化关系表查询告警、部件、故障原因和处理动作关系。"""

    def __init__(self, data_path: Path | None = None) -> None:
        """允许测试注入路径；默认读取阶段 2 图谱关系 fixture。"""
        self._data_path = (
            data_path or Path(__file__).parents[2] / "fixtures" / "graph_relations.json"
        )

    async def query_graph_relations(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """按告警名、设备类型和部件返回关系候选。"""
        alarm_name = payload.get("alarm_name")
        if not isinstance(alarm_name, str) or not alarm_name.strip():
            return self._not_found(context, "alarm_name 缺失或非法")

        device_type = payload.get("device_type")
        component = payload.get("component")
        top_k = self._positive_int(payload.get("top_k"), default=5)

        matches = [
            self._with_score(record, alarm_name, component)
            for record in self._load_records()
            if self._matches(record, alarm_name, device_type, component)
        ]
        ranked = sorted(matches, key=lambda item: item["score"], reverse=True)[:top_k]
        if not ranked:
            return self._not_found(context, "未召回匹配图谱关系")

        return ToolResult[Payload](
            success=True,
            status=ToolStatus.OK,
            data={"relations": ranked, "count": len(ranked)},
            meta=self._meta(context),
        )

    def _load_records(self) -> list[Payload]:
        """读取图谱关系 fixture；阶段 2 不依赖真实 Neo4j。"""
        raw: object = json.loads(self._data_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("graph relations fixture 必须是数组")

        records: list[Payload] = []
        for item in raw:
            if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
                raise ValueError("graph relations fixture 的每条记录必须是字符串键对象")
            records.append(cast(Payload, item))
        return records

    @staticmethod
    def _matches(
        record: Payload,
        alarm_name: str,
        device_type: object,
        component: object,
    ) -> bool:
        """执行确定性过滤，保证 Mock 结果可回归。"""
        if alarm_name not in str(record.get("alarm_name", "")):
            return False
        if (
            isinstance(device_type, str)
            and device_type
            and record.get("device_type") != device_type
        ):
            return False
        if (
            isinstance(component, str)
            and component
            and component not in str(record.get("component", ""))
        ):
            return False
        return True

    @staticmethod
    def _with_score(record: Payload, alarm_name: str, component: object) -> Payload:
        """把置信度和查询命中映射为阶段 2 可解释分数。"""
        confidence = record.get("confidence")
        base = confidence if isinstance(confidence, float | int) else 0.5
        score = float(base)
        if alarm_name == record.get("alarm_name"):
            score += 0.1
        if isinstance(component, str) and component and component == record.get("component"):
            score += 0.1
        enriched = dict(record)
        enriched["score"] = round(min(score, 1.0), 4)
        enriched["source_type"] = "graph"
        enriched["weak_evidence"] = True
        return enriched

    @staticmethod
    def _positive_int(value: object, *, default: int) -> int:
        """边界处兜底 top_k。"""
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return default

    @staticmethod
    def _meta(context: ToolContext) -> ToolMeta:
        """图谱 Mock 使用统一来源元数据，便于后续 Neo4j Adapter 复用契约。"""
        return ToolMeta(
            trace_id=context.trace_id,
            source_system="stage2-fixture",
            provider_type=ProviderType.MOCK,
        )

    def _not_found(self, context: ToolContext, message: str) -> ProviderResult:
        """图谱无结果不阻断主链路，用稳定状态表达降级基础。"""
        return ToolResult[Payload](
            success=False,
            status=ToolStatus.NOT_FOUND,
            data={"relations": [], "count": 0},
            meta=self._meta(context),
            error_code="GRAPH_RELATION_NOT_FOUND",
            error_message=message,
        )
