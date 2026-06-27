"""手册 chunk Mock 检索 Provider，提供阶段 2 基础关键词索引能力。"""

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


class MockManualSearchProvider:
    """在已解析 chunk 上做确定性关键词匹配，不实现阶段 3 RAG 重排。"""

    def __init__(self, data_path: Path | None = None) -> None:
        """允许测试注入路径；默认读取阶段 2 手册 chunk fixture。"""
        self._data_path = (
            data_path or Path(__file__).parents[2] / "fixtures" / "manuals" / "chunks.json"
        )

    async def search_manual_chunks(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """按 query、filters 和 top_k 返回手册片段。"""
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            return self._not_found(context, "query 缺失或非法")

        filters = payload.get("filters")
        filter_payload = filters if isinstance(filters, dict) else {}
        top_k = self._positive_int(payload.get("top_k"), default=5)
        threshold = self._score_threshold(payload.get("score_threshold"), default=0.0)

        matches = [
            self._with_score(record, query)
            for record in self._load_records()
            if self._matches_filters(record, filter_payload)
        ]
        ranked = [
            record
            for record in sorted(matches, key=lambda item: item["score"], reverse=True)
            if isinstance(record.get("score"), float)
            and record["score"] > 0
            and record["score"] >= threshold
        ][:top_k]

        if not ranked:
            return self._not_found(context, "未召回匹配手册 chunk")
        return ToolResult[Payload](
            success=True,
            status=ToolStatus.OK,
            data={"chunks": ranked, "count": len(ranked)},
            meta=self._meta(context),
        )

    def _load_records(self) -> list[Payload]:
        """读取解析后的手册 chunk；Mock 阶段不现场解析 PDF。"""
        raw: object = json.loads(self._data_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("manual chunks fixture 必须是数组")

        records: list[Payload] = []
        for item in raw:
            if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
                raise ValueError("manual chunks fixture 的每条记录必须是字符串键对象")
            records.append(cast(Payload, item))
        return records

    @staticmethod
    def _matches_filters(record: Payload, filters: dict[object, object]) -> bool:
        """仅实现阶段 2 元数据过滤，不做阶段 3 混合检索策略。"""
        for key in ("device_type", "device_model", "manufacturer", "alarm_name"):
            expected = filters.get(key)
            if isinstance(expected, str) and expected and record.get(key) != expected:
                return False
        section_type = filters.get("section_type")
        if isinstance(section_type, list):
            allowed = {item for item in section_type if isinstance(item, str)}
            if allowed and record.get("section_type") not in allowed:
                return False
        return True

    @staticmethod
    def _with_score(record: Payload, query: str) -> Payload:
        """用可解释的关键词命中率给分，避免提前实现 reranker。"""
        terms = {term.lower() for term in query.replace("/", " ").split() if term}
        haystack = " ".join(
            str(record.get(field, ""))
            for field in ("content", "device_type", "device_model", "chapter_title")
        ).lower()
        keywords = record.get("keywords")
        if isinstance(keywords, list):
            haystack = f"{haystack} {' '.join(str(item).lower() for item in keywords)}"
        hits = sum(1 for term in terms if term in haystack)
        score = 1.0 if not terms else min(1.0, hits / len(terms))
        enriched = dict(record)
        enriched["score"] = round(score, 4)
        enriched["source_type"] = "manual"
        return enriched

    @staticmethod
    def _positive_int(value: object, *, default: int) -> int:
        """边界处兜底 top_k，Provider 内部只消费稳定整数。"""
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return default

    @staticmethod
    def _score_threshold(value: object, *, default: float) -> float:
        """把非法阈值压回默认值，避免 Mock 检索被参数噪声打断。"""
        return (
            value
            if isinstance(value, float | int) and not isinstance(value, bool) and 0 <= value <= 1
            else default
        )

    @staticmethod
    def _meta(context: ToolContext) -> ToolMeta:
        """手册 Mock 保留来源元数据，后续可与 Milvus/OpenSearch Adapter 同契约。"""
        return ToolMeta(
            trace_id=context.trace_id,
            source_system="stage2-fixture",
            provider_type=ProviderType.MOCK,
        )

    def _not_found(self, context: ToolContext, message: str) -> ProviderResult:
        """检索未命中和参数缺失都用稳定检索错误码表达。"""
        return ToolResult[Payload](
            success=False,
            status=ToolStatus.NOT_FOUND,
            data={"chunks": [], "count": 0},
            meta=self._meta(context),
            error_code="RETRIEVAL_FAILED",
            error_message=message,
        )
