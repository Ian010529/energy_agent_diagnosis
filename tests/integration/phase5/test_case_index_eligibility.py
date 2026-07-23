import os
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import delete

from energy_agent.core.ids import new_id
from energy_agent.graph.service import GraphService
from energy_agent.indexing.contracts import (
    EntityType,
    IndexJobMessage,
    IndexOperation,
)
from energy_agent.indexing.handler_runtime import IndexHandlerRuntime, StaleIndexEventError
from energy_agent.persistence.models import DiagnosisCaseModel
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory

pytestmark = pytest.mark.integration
MYSQL_DSN = os.getenv(
    "TEST_MYSQL_DSN", "mysql+aiomysql://energy:energy_dev@localhost:3306/energy_agent"
)


class _Embedding:
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[0.01] * 1024 for _ in texts]


class _Milvus:
    def __init__(self) -> None:
        self.calls = 0

    async def upsert(self, source: str, rows: list[dict[str, object]]) -> None:
        self.calls += 1

    async def delete(self, source: str, ids: list[str]) -> None:
        pass


@pytest_asyncio.fixture
async def mysql_factory():
    engine = create_mysql_engine(MYSQL_DSN)
    factory = create_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_rejected_case_is_never_indexed(mysql_factory) -> None:
    case_id = new_id()
    now = datetime.now(UTC).replace(tzinfo=None)
    async with mysql_factory.begin() as session:
        session.add(
            DiagnosisCaseModel(
                case_id=case_id,
                source_session_id=new_id(),
                source_run_id=new_id(),
                source_review_id=new_id(),
                device_type="PCS",
                device_model="SC5000",
                alarm_name="风扇异常",
                symptom_summary="风扇停转",
                root_cause="风扇故障",
                resolution_steps=["更换风扇"],
                safety_notes=[],
                evidence_refs=["evidence-1"],
                review_status="REJECTED",
                case_version=1,
                index_status="PENDING",
                is_active=False,
                created_by="operator",
                created_at=now,
                updated_at=now,
            )
        )
    embedding = _Embedding()
    milvus = _Milvus()
    runtime = IndexHandlerRuntime(
        session_factory=mysql_factory,
        embedding=embedding,
        milvus=milvus,
        graph=GraphService(None),
    )
    event = IndexJobMessage(
        job_id=new_id(),
        entity_type=EntityType.DIAGNOSIS_CASE,
        entity_id=case_id,
        entity_version="1",
        operation=IndexOperation.UPSERT,
        trace_id=new_id(),
        correlation_id=new_id(),
        causation_id=new_id(),
        requested_at=datetime.now(UTC),
    )
    try:
        with pytest.raises(StaleIndexEventError, match="INDEX_EVENT_STALE"):
            await runtime.handle(event)
        assert embedding.calls == 0
        assert milvus.calls == 0
        async with mysql_factory() as session:
            case = await session.get(DiagnosisCaseModel, case_id)
            assert case is not None
            assert case.review_status == "REJECTED"
            assert case.index_status == "PENDING"
            assert case.is_active is False
    finally:
        async with mysql_factory.begin() as session:
            await session.execute(
                delete(DiagnosisCaseModel).where(DiagnosisCaseModel.case_id == case_id)
            )
