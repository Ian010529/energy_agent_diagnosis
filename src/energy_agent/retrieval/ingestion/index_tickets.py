import asyncio
import re
from typing import Any

from sqlalchemy import select, update

from energy_agent.bootstrap.lifespan import create_tracer
from energy_agent.core.config import Settings
from energy_agent.core.ids import new_id
from energy_agent.core.time import utc_now
from energy_agent.indexing.contracts import EntityType, IndexJobCreate, IndexOperation
from energy_agent.indexing.repository import IndexRepository
from energy_agent.persistence.models import MaintenanceTicketModel
from energy_agent.persistence.mysql import create_mysql_engine, create_session_factory
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.milvus import MilvusVectorProvider


def build_ticket_embedding_text(ticket: dict[str, object]) -> str:
    fields = (
        ticket.get("device_model"),
        ticket.get("alarm_name"),
        ticket.get("fault_symptom"),
        ticket.get("root_cause"),
        ticket.get("action_taken"),
    )
    return re.sub(r"\s+", " ", " ".join(str(value) for value in fields if value)).strip()


async def run() -> None:
    settings = Settings()
    if settings.embedding_mode != "openai_compatible":
        raise RuntimeError("Ticket indexing requires EMBEDDING_MODE=openai_compatible")
    tracer = create_tracer(settings)
    engine = create_mysql_engine(settings.mysql_dsn)
    factory = create_session_factory(engine)
    index_repository = IndexRepository(factory, tracer)
    embedding = OpenAICompatibleEmbeddingProvider(
        base_url=settings.embedding_base_url or "",
        api_key=settings.embedding_api_key or "",
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        timeout_seconds=settings.embedding_timeout_seconds,
        batch_size=settings.embedding_batch_size,
    )
    milvus = MilvusVectorProvider(
        uri=settings.milvus_uri,
        token=settings.milvus_token,
        manual_collection=settings.milvus_manual_collection,
        ticket_collection=settings.milvus_ticket_collection,
        dimension=settings.milvus_vector_dimension,
        metric_type=settings.milvus_metric_type,
    )
    generation = new_id()
    try:
        if settings.index_execution_mode == "rabbitmq":
            async with factory() as session:
                tickets = (
                    (
                        await session.execute(
                            select(MaintenanceTicketModel).where(
                                MaintenanceTicketModel.is_verified.is_(True)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
            queued = 0
            for ticket in tickets:
                generation = new_id()
                trace_id = f"ticket-index-{generation}"
                async with factory.begin() as session:
                    current = await session.get(
                        MaintenanceTicketModel,
                        ticket.ticket_id,
                        with_for_update=True,
                    )
                    if not current or not current.is_verified:
                        continue
                    current.index_generation = generation
                    current.index_status = "QUEUED"
                    current.index_error_code = None
                    current.updated_at = utc_now()
                    await index_repository.add_job(
                        session,
                        IndexJobCreate(
                            entity_type=EntityType.MAINTENANCE_TICKET,
                            entity_id=current.ticket_id,
                            entity_version=generation,
                            operation=IndexOperation.UPSERT,
                            trace_id=trace_id,
                            correlation_id=current.ticket_id,
                            causation_id=generation,
                            max_attempts=settings.index_max_attempts,
                        ),
                    )
                    queued += 1
            print(f"TICKET_QUEUED={queued}")
            return
        await milvus.ensure_collections()
        async with factory() as session:
            tickets = (
                (
                    await session.execute(
                        select(MaintenanceTicketModel).where(
                            MaintenanceTicketModel.is_verified.is_(True)
                        )
                    )
                )
                .scalars()
                .all()
            )
        texts = [
            build_ticket_embedding_text(
                {
                    column.name: getattr(ticket, column.name)
                    for column in MaintenanceTicketModel.__table__.columns
                }
            )
            for ticket in tickets
        ]
        with tracer.start_span(
            "retrieval.ticket_index",
            trace_id=f"ticket-index-{generation}",
            metadata={"ticket_count": len(tickets), "index_generation": generation},
        ):
            vectors = await embedding.embed(texts) if texts else []
            rows: list[dict[str, Any]] = [
                {
                    "id": ticket.ticket_id,
                    "source_id": ticket.ticket_id,
                    "device_type": "",
                    "device_model": ticket.device_model,
                    "manufacturer": ticket.manufacturer or "",
                    "alarm_name": ticket.alarm_name,
                    "index_generation": generation,
                    "verified": True,
                    "effective": True,
                    "close_time": int(ticket.close_time.timestamp()) if ticket.close_time else 0,
                    "embedding": vector,
                }
                for ticket, vector in zip(tickets, vectors, strict=True)
            ]
            await milvus.upsert("ticket", rows)
        now = utc_now()
        async with factory() as session, session.begin():
            for ticket, text in zip(tickets, texts, strict=True):
                await session.execute(
                    update(MaintenanceTicketModel)
                    .where(MaintenanceTicketModel.ticket_id == ticket.ticket_id)
                    .values(
                        embedding_text=text,
                        index_status="INDEXED",
                        index_error_code=None,
                        embedding_model=settings.embedding_model,
                        embedding_dimension=settings.embedding_dimension,
                        indexed_at=now,
                        updated_at=now,
                    )
                )
        print(f"TICKET_INDEXED={len(tickets)}")
    finally:
        await embedding.close()
        await milvus.close()
        await engine.dispose()
        await tracer.flush()
        await tracer.shutdown()


if __name__ == "__main__":
    asyncio.run(run())
