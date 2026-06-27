"""历史工单 Mock 检索 Provider，提供阶段 2 工单清洗后的查询基线。"""

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


class MockTicketSearchProvider:
    """在脱敏工单样例上做简单相似检索，区分已审核和弱参考。"""

    def __init__(self, data_path: Path | None = None) -> None:
        """允许测试注入路径；默认读取阶段 2 工单 fixture。"""
        self._data_path = data_path or Path(__file__).parents[2] / "fixtures" / "tickets.json"

    async def search_similar_tickets(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """按 query、filters 和 verified_only 返回相似工单。"""
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            return self._not_found(context, "query 缺失或非法")

        filters = payload.get("filters")
        filter_payload = filters if isinstance(filters, dict) else {}
        raw_verified_only = payload.get("verified_only", True)
        verified_only = raw_verified_only if isinstance(raw_verified_only, bool) else True
        top_k = self._positive_int(payload.get("top_k"), default=5)
        threshold = self._score_threshold(payload.get("score_threshold"), default=0.0)

        matches = [
            self._with_score(record, query)
            for record in self._load_records()
            if self._matches_filters(record, filter_payload)
            and (verified_only is not True or record.get("is_verified") is True)
        ]
        ranked = [
            record
            for record in sorted(matches, key=lambda item: item["score"], reverse=True)
            if isinstance(record.get("score"), float)
            and record["score"] > 0
            and record["score"] >= threshold
        ][:top_k]

        if not ranked:
            return self._not_found(context, "未召回匹配历史工单")
        return ToolResult[Payload](
            success=True,
            status=ToolStatus.OK,
            data={"tickets": ranked, "count": len(ranked)},
            meta=self._meta(context),
        )

    def _load_records(self) -> list[Payload]:
        """读取清洗后的工单样例；未审核工单仍保留，但默认不做强证据。"""
        raw: object = json.loads(self._data_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("tickets fixture 必须是数组")

        records: list[Payload] = []
        for item in raw:
            if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
                raise ValueError("tickets fixture 的每条记录必须是字符串键对象")
            records.append(cast(Payload, item))
        return records

    @staticmethod
    def _matches_filters(record: Payload, filters: dict[object, object]) -> bool:
        """阶段 2 只做结构化过滤，不引入阶段 3 向量相似检索。"""
        for key in ("device_type", "device_model", "alarm_name", "manufacturer", "site_id"):
            expected = filters.get(key)
            if isinstance(expected, str) and expected and record.get(key) != expected:
                return False
        excluded = filters.get("exclude_ticket_ids")
        if isinstance(excluded, list) and record.get("ticket_id") in excluded:
            return False
        return True

    @staticmethod
    def _with_score(record: Payload, query: str) -> Payload:
        """用简单关键词命中率排序，保留后续替换为真实检索的接口空间。"""
        terms = {term.lower() for term in query.replace("/", " ").split() if term}
        searchable_fields = (
            "device_model",
            "alarm_name",
            "fault_symptom",
            "root_cause",
            "action_taken",
        )
        haystack = " ".join(str(record.get(field, "")) for field in searchable_fields).lower()
        hits = sum(1 for term in terms if term in haystack)
        score = 1.0 if not terms else min(1.0, hits / len(terms))
        enriched = dict(record)
        enriched["score"] = round(score, 4)
        enriched["source_type"] = "ticket"
        enriched["weak_evidence"] = record.get("is_verified") is not True
        return enriched

    @staticmethod
    def _positive_int(value: object, *, default: int) -> int:
        """边界处兜底 top_k，避免无效参数扩散进检索逻辑。"""
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return default

    @staticmethod
    def _score_threshold(value: object, *, default: float) -> float:
        """非法阈值使用默认值，保持 Mock 行为稳定可回归。"""
        return (
            value
            if isinstance(value, float | int) and not isinstance(value, bool) and 0 <= value <= 1
            else default
        )

    @staticmethod
    def _meta(context: ToolContext) -> ToolMeta:
        """工单 Mock 使用同一元数据契约，便于后续真实工单系统替换。"""
        return ToolMeta(
            trace_id=context.trace_id,
            source_system="stage2-fixture",
            provider_type=ProviderType.MOCK,
        )

    def _not_found(self, context: ToolContext, message: str) -> ProviderResult:
        """检索未命中用标准错误码表达，不把低质量工单强行补进结果。"""
        return ToolResult[Payload](
            success=False,
            status=ToolStatus.NOT_FOUND,
            data={"tickets": [], "count": 0},
            meta=self._meta(context),
            error_code="RETRIEVAL_FAILED",
            error_message=message,
        )
