from datetime import UTC, datetime
from typing import Any

import pytest

from energy_agent.evaluation.drain_index_queue import (
    EvaluationBatchDrainer,
    PendingMessage,
)
from energy_agent.indexing.contracts import (
    EntityType,
    IndexJobMessage,
    IndexJobStatus,
    IndexOperation,
)
from energy_agent.indexing.handlers import HandlerResult, PermanentIndexError


class _Message:
    def __init__(self) -> None:
        self.acked = False

    async def ack(self) -> None:
        self.acked = True


class _Repository:
    def __init__(self) -> None:
        self.finished: list[tuple[str, IndexJobStatus]] = []
        self.failures: list[dict[str, Any]] = []

    async def finish(self, job_id: str, status: IndexJobStatus) -> None:
        self.finished.append((job_id, status))

    async def fail(self, job_id: str, **kwargs: Any) -> None:
        self.failures.append({"job_id": job_id, **kwargs})


class _Handlers:
    async def handle_batch(self, events: list[IndexJobMessage]) -> dict[str, HandlerResult]:
        if len(events) > 1:
            raise RuntimeError("split")
        if events[0].entity_id == "bad":
            raise PermanentIndexError("INDEX_ENTITY_NOT_FOUND")
        return {events[0].job_id: HandlerResult(IndexJobStatus.INDEXED)}


class _Rabbit:
    dead_routing_key = "dead"
    retry_routing_key = "retry"

    def __init__(self) -> None:
        self.published: list[str | None] = []

    async def publish(self, payload: bytes, *, routing_key: str | None = None) -> None:
        del payload
        self.published.append(routing_key)


def _pending(entity_id: str) -> PendingMessage:
    event = IndexJobMessage(
        job_id=f"job-{entity_id}",
        entity_type=EntityType.MAINTENANCE_TICKET,
        entity_id=entity_id,
        entity_version="1.3.0",
        operation=IndexOperation.UPSERT,
        trace_id=f"trace-{entity_id}",
        correlation_id=entity_id,
        causation_id=entity_id,
        requested_at=datetime.now(UTC),
    )
    return PendingMessage(
        message=_Message(),  # type: ignore[arg-type]
        event=event,
        attempt_count=1,
        max_attempts=3,
    )


@pytest.mark.asyncio
async def test_evaluation_batch_drainer_splits_and_dead_letters_permanent_failure() -> None:
    repository = _Repository()
    rabbit = _Rabbit()
    good = _pending("good")
    bad = _pending("bad")
    drainer = EvaluationBatchDrainer(
        repository=repository,  # type: ignore[arg-type]
        handlers=_Handlers(),  # type: ignore[arg-type]
        rabbitmq=rabbit,  # type: ignore[arg-type]
        retry_delay_ms=5000,
    )

    await drainer._process([good, bad])

    assert repository.finished == [("job-good", IndexJobStatus.INDEXED)]
    assert repository.failures[0]["job_id"] == "job-bad"
    assert repository.failures[0]["retry_delay_ms"] is None
    assert rabbit.published == ["dead"]
    assert good.message.acked is True  # type: ignore[attr-defined]
    assert bad.message.acked is True  # type: ignore[attr-defined]
    assert drainer.completed == 1
    assert drainer.failed == 1
