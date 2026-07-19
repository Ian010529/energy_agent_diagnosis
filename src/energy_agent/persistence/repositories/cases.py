from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from energy_agent.contracts.cases import (
    CaseIndexStatus,
    CaseReviewEvent,
    CaseStatus,
    DiagnosisCase,
)
from energy_agent.core.errors import (
    CaseNotEditableError,
    CaseNotFoundError,
    CaseStateConflictError,
)
from energy_agent.core.time import ensure_utc, utc_now
from energy_agent.indexing.contracts import IndexJobCreate
from energy_agent.indexing.repository import IndexRepository
from energy_agent.persistence.models import CaseReviewEventModel, DiagnosisCaseModel


def case_record(model: DiagnosisCaseModel) -> DiagnosisCase:
    data = {
        column.name: getattr(model, column.name) for column in DiagnosisCaseModel.__table__.columns
    }
    data["created_at"] = ensure_utc(model.created_at)
    data["updated_at"] = ensure_utc(model.updated_at)
    return DiagnosisCase.model_validate(data)


class CaseRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        index_repository: IndexRepository | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.index_repository = index_repository

    async def create(self, values: dict[str, object]) -> DiagnosisCase:
        now = utc_now()
        model = DiagnosisCaseModel(**values, created_at=now, updated_at=now)
        async with self.session_factory.begin() as session:
            session.add(model)
        return case_record(model)

    async def get(self, case_id: str) -> DiagnosisCase | None:
        async with self.session_factory() as session:
            model = await session.get(DiagnosisCaseModel, case_id)
        return case_record(model) if model else None

    async def get_by_review(self, review_id: str) -> DiagnosisCase | None:
        async with self.session_factory() as session:
            model = (
                await session.execute(
                    select(DiagnosisCaseModel).where(
                        DiagnosisCaseModel.source_review_id == review_id
                    )
                )
            ).scalar_one_or_none()
        return case_record(model) if model else None

    async def list_cases(self, filters: dict[str, object]) -> list[DiagnosisCase]:
        query = select(DiagnosisCaseModel)
        for name in (
            "review_status",
            "device_type",
            "device_model",
            "alarm_name",
            "created_by",
            "is_active",
        ):
            value = filters.get(name)
            if value is not None:
                query = query.where(getattr(DiagnosisCaseModel, name) == value)
        query = query.order_by(DiagnosisCaseModel.created_at.desc())
        async with self.session_factory() as session:
            rows = (await session.execute(query)).scalars().all()
        return [case_record(row) for row in rows]

    async def update_draft(
        self, case_id: str, values: dict[str, object], actor_id: str, *, privileged: bool
    ) -> DiagnosisCase:
        async with self.session_factory.begin() as session:
            model = await session.get(DiagnosisCaseModel, case_id)
            if model is None:
                raise CaseNotFoundError("Case not found")
            if model.review_status != CaseStatus.DRAFT:
                raise CaseNotEditableError("Only DRAFT cases are editable")
            if model.created_by != actor_id and not privileged:
                raise CaseNotEditableError("Only the creator or a reviewer may edit the draft")
            for key, value in values.items():
                setattr(model, key, value)
            model.updated_at = utc_now()
        return case_record(model)

    async def transition(
        self,
        case_id: str,
        *,
        expected: CaseStatus,
        target: CaseStatus,
        actor_id: str,
        actor_role: str,
        action: str,
        trace_id: str,
        request_hash: str,
        idempotency_key: str | None,
        comment: str | None = None,
        updates: dict[str, object] | None = None,
        index_request: IndexJobCreate | None = None,
    ) -> DiagnosisCase:
        async with self.session_factory.begin() as session:
            if idempotency_key:
                existing = (
                    await session.execute(
                        select(CaseReviewEventModel).where(
                            CaseReviewEventModel.case_id == case_id,
                            CaseReviewEventModel.idempotency_key == idempotency_key,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    if existing.request_hash != request_hash:
                        raise CaseStateConflictError(
                            "Idempotency key reused with different request"
                        )
                    model = await session.get(DiagnosisCaseModel, case_id)
                    assert model is not None
                    return case_record(model)
            model = await session.get(DiagnosisCaseModel, case_id, with_for_update=True)
            if model is None:
                raise CaseNotFoundError("Case not found")
            if model.review_status != expected:
                raise CaseStateConflictError(
                    f"Case state must be {expected}, got {model.review_status}"
                )
            previous = model.review_status
            model.review_status = target
            for key, value in (updates or {}).items():
                setattr(model, key, value)
            model.updated_at = utc_now()
            session.add(
                CaseReviewEventModel(
                    case_id=case_id,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action=action,
                    from_status=previous,
                    to_status=target,
                    comment=comment,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    trace_id=trace_id,
                    created_at=utc_now(),
                )
            )
            index_job_id: str | None = None
            if index_request:
                if not self.index_repository:
                    raise RuntimeError("index repository is unavailable")
                job = await self.index_repository.add_job(session, index_request)
                index_job_id = job.job_id
        record = case_record(model)
        return record.model_copy(update={"index_job_id": index_job_id})

    async def queue_index(
        self,
        case_id: str,
        *,
        request: IndexJobCreate,
        actor_id: str,
        actor_role: str,
        action: str,
        trace_id: str,
        request_hash: str,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        if not self.index_repository:
            raise RuntimeError("index repository is unavailable")
        async with self.session_factory.begin() as session:
            model = await session.get(DiagnosisCaseModel, case_id, with_for_update=True)
            if not model:
                raise CaseNotFoundError("Case not found")
            model.index_status = CaseIndexStatus.QUEUED
            model.is_active = False
            model.updated_at = utc_now()
            session.add(
                CaseReviewEventModel(
                    case_id=case_id,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action=action,
                    from_status=model.review_status,
                    to_status=model.review_status,
                    comment=None,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    trace_id=trace_id,
                    created_at=utc_now(),
                )
            )
            job = await self.index_repository.add_job(session, request)
        return case_record(model).model_copy(update={"index_job_id": job.job_id})

    async def find_idempotent_event(
        self, case_id: str, idempotency_key: str
    ) -> CaseReviewEventModel | None:
        async with self.session_factory() as session:
            return (
                await session.execute(
                    select(CaseReviewEventModel).where(
                        CaseReviewEventModel.case_id == case_id,
                        CaseReviewEventModel.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()

    async def append_event(
        self,
        *,
        case_id: str,
        actor_id: str,
        actor_role: str,
        action: str,
        from_status: CaseStatus,
        to_status: CaseStatus,
        comment: str | None,
        idempotency_key: str | None,
        request_hash: str,
        trace_id: str,
    ) -> None:
        async with self.session_factory.begin() as session:
            session.add(
                CaseReviewEventModel(
                    case_id=case_id,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    action=action,
                    from_status=from_status,
                    to_status=to_status,
                    comment=comment,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    trace_id=trace_id,
                    created_at=utc_now(),
                )
            )

    async def set_index(
        self,
        case_id: str,
        status: CaseIndexStatus,
        *,
        error_code: str | None = None,
        embedding_text: str | None = None,
        active: bool | None = None,
    ) -> DiagnosisCase:
        async with self.session_factory.begin() as session:
            model = await session.get(DiagnosisCaseModel, case_id, with_for_update=True)
            if model is None:
                raise CaseNotFoundError("Case not found")
            model.index_status = status
            model.index_error_code = error_code
            if embedding_text is not None:
                model.embedding_text = embedding_text
            if active is not None:
                model.is_active = active
            model.updated_at = utc_now()
        return case_record(model)

    async def next_version(self, session_id: str) -> int:
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(DiagnosisCaseModel.case_version).where(
                        DiagnosisCaseModel.source_session_id == session_id
                    )
                )
            ).scalars()
            return max(rows, default=0) + 1

    async def history(self, case_id: str) -> list[CaseReviewEvent]:
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(CaseReviewEventModel)
                    .where(CaseReviewEventModel.case_id == case_id)
                    .order_by(CaseReviewEventModel.created_at)
                )
            ).scalars()
            return [
                CaseReviewEvent.model_validate(
                    {
                        "id": row.id,
                        "case_id": row.case_id,
                        "actor_id": row.actor_id,
                        "actor_role": row.actor_role,
                        "action": row.action,
                        "from_status": row.from_status,
                        "to_status": row.to_status,
                        "comment": row.comment,
                        "trace_id": row.trace_id,
                        "created_at": ensure_utc(row.created_at),
                    }
                )
                for row in rows
            ]
