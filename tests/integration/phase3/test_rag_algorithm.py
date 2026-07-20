from datetime import UTC, datetime

import pytest

from energy_agent.agent.state import AlarmContext, DeviceContext, DiagnosisState
from energy_agent.agent.workflow import build_diagnosis_graph
from energy_agent.contracts.common import DiagnosisPhase, SessionSource
from energy_agent.core.errors import MilvusUnavailableError, RerankerUnavailableError
from energy_agent.observability.tracing import LocalTracer
from energy_agent.retrieval.contracts import RetrievalMode, SourceType
from energy_agent.retrieval.service import RetrievalService
from energy_agent.tools.executor import ToolExecutor
from energy_agent.tools.implementations.read_tools import build_registry

pytestmark = pytest.mark.integration


class FakeMySQL:
    async def get_device(self, device_id: str) -> dict[str, object]:
        return {
            "device_id": device_id,
            "site_id": "SITE-1",
            "device_type": "PCS",
            "device_model": "SC5000",
            "manufacturer": "EnergyCo",
            "status": "online",
        }

    async def get_alarm(self, alarm_id: str, device_id: str | None) -> dict[str, object]:
        return {
            "alarm_id": alarm_id,
            "device_id": device_id or "PCS-1",
            "alarm_name": "温度告警",
            "alarm_level": "high",
            "trigger_time": datetime.now(UTC),
        }

    async def manual_candidates(
        self,
        filters: dict[str, object],
        *,
        effective_only: bool = True,
        strong_only: bool = False,
    ) -> list[dict[str, object]]:
        return [
            {
                "chunk_id": "M-1",
                "doc_id": "DOC-1",
                "device_type": "PCS",
                "device_model": "SC5000",
                "manufacturer": "EnergyCo",
                "alarm_name": "温度告警",
                "chapter_title": "散热维护",
                "page_no": 3,
                "section_type": "维护步骤",
                "summary_or_content": "温度告警时检查散热风扇、滤网和风道。",
                "version": "1",
                "verified": True,
                "effective": True,
                "index_generation": "g1",
            }
        ]

    async def ticket_candidates(
        self, filters: dict[str, object], *, verified_only: bool = True
    ) -> list[dict[str, object]]:
        return [
            {
                "ticket_id": "T-1",
                "site_id": "SITE-1",
                "device_model": "SC5000",
                "manufacturer": "EnergyCo",
                "alarm_name": "温度告警",
                "fault_symptom": "温度持续上升且风扇停转",
                "root_cause": "散热风扇供电故障",
                "action_taken": "更换风扇",
                "is_verified": True,
                "close_time": datetime.now(UTC),
                "index_generation": "g1",
            }
        ]


class FakeEmbedding:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[1.0] + [0.0] * 1023 for _ in texts]


class FakeMilvus:
    async def search(
        self, source: str, vector: list[float], allowed_ids: list[str], limit: int
    ) -> list[dict[str, object]]:
        return [
            {"id": identifier, "source_id": identifier, "vector_score": 0.9}
            for identifier in allowed_ids[:limit]
        ]


class FailingMilvus(FakeMilvus):
    async def search(
        self, source: str, vector: list[float], allowed_ids: list[str], limit: int
    ) -> list[dict[str, object]]:
        raise MilvusUnavailableError("offline")


class FakeReranker:
    async def rerank(self, query: str, candidates: list[tuple[str, str]]) -> dict[str, float]:
        return {identifier: 0.95 - index * 0.05 for index, (identifier, _) in enumerate(candidates)}


class FakeInflux:
    async def query(
        self,
        device_id: str,
        metrics: list[str],
        start_time: str,
        end_time: str,
        max_points: int,
        measurements: list[str] | None = None,
    ) -> dict[str, dict[str, object]]:
        return {
            metric: {
                "missing": False,
                "trend": "rising" if metric == "cabinet_temperature" else "stable",
                "point_count": 3,
            }
            for metric in metrics
        }


class FailingReranker(FakeReranker):
    async def rerank(self, query: str, candidates: list[tuple[str, str]]) -> dict[str, float]:
        raise RerankerUnavailableError("offline")


@pytest.mark.asyncio
async def test_hybrid_manual_ticket_merge_rerank_score_and_fallbacks() -> None:
    filters = {
        "device_type": "PCS",
        "device_model": "SC5000",
        "manufacturer": "EnergyCo",
        "alarm_name": "温度告警",
    }
    embedding = FakeEmbedding()
    service = RetrievalService(
        mysql=FakeMySQL(),  # type: ignore[arg-type]
        tracer=LocalTracer(),
        embedding=embedding,  # type: ignore[arg-type]
        milvus=FakeMilvus(),  # type: ignore[arg-type]
        reranker=FakeReranker(),  # type: ignore[arg-type]
        default_mode=RetrievalMode.HYBRID,
    )
    manual = await service.search(
        SourceType.MANUAL,
        "PCS 温度高",
        filters,
        trace_id="trace-hybrid",
        mode=RetrievalMode.HYBRID,
        score_threshold=0.45,
    )
    ticket = await service.search(
        SourceType.TICKET,
        "PCS 温度高",
        filters,
        trace_id="trace-hybrid",
        mode=RetrievalMode.HYBRID,
        score_threshold=0.45,
    )
    assert manual.retrieval_metadata.retrieval_mode == RetrievalMode.HYBRID
    assert manual.retrieval_metadata.rerank_applied is True
    assert manual.retrieval_metadata.degraded_components == []
    assert manual.ranked_evidence[0].final_score > 0.45
    assert ticket.ranked_evidence[0].source_type == SourceType.TICKET
    assert len(embedding.calls) == 1
    assert len(embedding.calls[0]) == 2

    degraded = RetrievalService(
        mysql=FakeMySQL(),  # type: ignore[arg-type]
        tracer=LocalTracer(),
        embedding=FakeEmbedding(),  # type: ignore[arg-type]
        milvus=FailingMilvus(),  # type: ignore[arg-type]
        reranker=FailingReranker(),  # type: ignore[arg-type]
    )
    fallback = await degraded.search(
        SourceType.MANUAL,
        "PCS 温度高",
        filters,
        trace_id="trace-fallback",
        mode=RetrievalMode.HYBRID,
        score_threshold=0.45,
    )
    assert fallback.retrieval_metadata.retrieval_mode == RetrievalMode.KEYWORD_ONLY
    assert fallback.retrieval_metadata.partial_result is True
    assert {"embedding", "milvus"} <= set(fallback.retrieval_metadata.degraded_components)


@pytest.mark.asyncio
async def test_existing_langgraph_completes_with_full_hybrid_without_vector_degradation() -> None:
    tracer = LocalTracer()
    mysql = FakeMySQL()
    retrieval = RetrievalService(
        mysql=mysql,  # type: ignore[arg-type]
        tracer=tracer,
        embedding=FakeEmbedding(),  # type: ignore[arg-type]
        milvus=FakeMilvus(),  # type: ignore[arg-type]
        reranker=FakeReranker(),  # type: ignore[arg-type]
        default_mode=RetrievalMode.HYBRID,
    )
    registry = build_registry(
        mysql,  # type: ignore[arg-type]
        FakeInflux(),  # type: ignore[arg-type]
        tracer,
        retrieval,
    )

    async def memory_writer(_: DiagnosisState) -> None:
        return None

    graph = build_diagnosis_graph(
        ToolExecutor(registry, tracer),
        tracer,
        memory_writer=memory_writer,
    )
    output = await graph.ainvoke(
        DiagnosisState(
            session_id="session-phase3",
            run_id="run-phase3",
            trace_id="trace-phase3",
            source=SessionSource.ALARM,
            user_message="请诊断 PCS 温度高",
            device_context=DeviceContext(site_id="SITE-1", device_id="PCS-1"),
            alarm_context=AlarmContext(
                alarm_id="ALARM-1",
                alarm_name="温度告警",
            ),
        )
    )
    state = DiagnosisState.model_validate(output)
    assert state.phase == DiagnosisPhase.COMPLETED
    assert state.degraded_components == ["neo4j"]
    assert "vector_retrieval" not in state.degraded_components
    assert {item.source_type for item in state.evidence} >= {"manual", "ticket"}
