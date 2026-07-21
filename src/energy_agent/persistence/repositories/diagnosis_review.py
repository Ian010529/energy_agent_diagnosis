from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.core.errors import IdempotencyConflictError
from energy_agent.core.time import ensure_utc, utc_now
from energy_agent.persistence.models import DiagnosisReviewModel


class DiagnosisReviewRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def append(self, values: dict[str, object]) -> DiagnosisReviewModel:
        session_id = str(values["session_id"])
        key = values.get("idempotency_key")
        async with self.session_factory.begin() as session:
            if key:
                existing = (
                    await session.execute(
                        select(DiagnosisReviewModel).where(
                            DiagnosisReviewModel.session_id == session_id,
                            DiagnosisReviewModel.idempotency_key == key,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    if existing.request_hash != values["request_hash"]:
                        raise IdempotencyConflictError(
                            "Idempotency key reused with different request"
                        )
                    return existing
            model = DiagnosisReviewModel(**values, created_at=utc_now())
            session.add(model)
        return model

    async def list_by_session(self, session_id: str) -> list[DiagnosisReviewModel]:
        async with self.session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(DiagnosisReviewModel)
                        .where(DiagnosisReviewModel.session_id == session_id)
                        .order_by(DiagnosisReviewModel.created_at, DiagnosisReviewModel.review_id)
                    )
                )
                .scalars()
                .all()
            )
        return list(rows)

    @staticmethod
    def created_at(model: DiagnosisReviewModel) -> datetime:
        return ensure_utc(model.created_at)
