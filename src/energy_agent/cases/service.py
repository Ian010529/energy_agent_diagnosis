from fastapi import Request

from energy_agent.contracts.cases import (
    CaseDisableRequest,
    CaseIndexStatus,
    CasePatchRequest,
    CaseReviewEvent,
    CaseReviewRequest,
    CaseRevisionRequest,
    CaseStatus,
    DiagnosisCase,
    DiagnosisReviewRequest,
    DiagnosisReviewResponse,
    DiagnosisReviewResult,
)
from energy_agent.contracts.common import DiagnosisPhase
from energy_agent.contracts.diagnosis import DiagnosisResultRecord, DiagnosisSessionUpdate
from energy_agent.core.context import ActorContext, ActorRole, get_context
from energy_agent.core.errors import (
    CaseNotEditableError,
    CaseNotFoundError,
    CaseNotIndexedError,
    CaseNotReadyError,
    CaseStateConflictError,
    DiagnosisReviewInvalidError,
    InvalidEvidenceReferenceError,
    RootCauseOverrideReasonRequiredError,
    SelfReviewForbiddenError,
    SessionNotReviewableError,
)
from energy_agent.core.idempotency import request_fingerprint
from energy_agent.core.ids import new_id
from energy_agent.core.time import utc_now
from energy_agent.indexing.contracts import (
    EntityType,
    IndexJobCreate,
    IndexOperation,
)
from energy_agent.observability.metrics import HUMAN_REVIEWS
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.repositories.audit import AuditRepository
from energy_agent.persistence.repositories.cases import CaseRepository
from energy_agent.persistence.repositories.diagnosis_run import DiagnosisResultRepository
from energy_agent.persistence.repositories.diagnosis_session import DiagnosisSessionRepository
from energy_agent.providers.embedding import OpenAICompatibleEmbeddingProvider
from energy_agent.providers.milvus import MilvusVectorProvider
from energy_agent.timeline.contracts import TimelineEventCreate, TimelineEventType
from energy_agent.timeline.repository import TimelineRepository, timeline_event_id
from energy_agent.tools.executor import ToolExecutor
from energy_agent.tools.registry import ToolRegistry


def build_embedding_text(case: DiagnosisCase) -> str:
    parts = (
        case.device_type,
        case.device_model,
        case.alarm_name,
        case.symptom_summary,
        case.timeseries_features,
        case.root_cause,
        "；".join(case.resolution_steps),
    )
    return "\n".join(str(item).strip() for item in parts if item and str(item).strip())


def missing_case_fields(case: DiagnosisCase, valid_evidence: set[str]) -> list[str]:
    required = {
        "device_type": case.device_type,
        "device_model": case.device_model,
        "alarm_name": case.alarm_name,
        "symptom_summary": case.symptom_summary,
        "root_cause": case.root_cause,
        "resolution_steps": case.resolution_steps,
        "evidence_refs": case.evidence_refs,
        "created_by": case.created_by,
    }
    missing = [name for name, value in required.items() if not value]
    if any(ref not in valid_evidence for ref in case.evidence_refs):
        missing.append("valid_evidence_refs")
    return missing


class CaseService:
    def __init__(
        self,
        *,
        cases: CaseRepository,
        sessions: DiagnosisSessionRepository,
        results: DiagnosisResultRepository,
        audit: AuditRepository,
        tools: ToolRegistry,
        tracer: Tracer,
        embedding: OpenAICompatibleEmbeddingProvider | None,
        milvus: MilvusVectorProvider | None,
        index_execution_mode: str = "sync",
        index_max_attempts: int = 3,
        timeline: TimelineRepository | None = None,
    ) -> None:
        self.cases = cases
        self.sessions = sessions
        self.results = results
        self.audit = audit
        self.tools = tools
        self.tracer = tracer
        self.embedding = embedding
        self.milvus = milvus
        self.index_execution_mode = index_execution_mode
        self.index_max_attempts = index_max_attempts
        self.timeline = timeline

    @classmethod
    def from_request(cls, request: Request) -> "CaseService":
        state = request.app.state
        return cls(
            cases=state.case_repository,
            sessions=state.session_repository,
            results=state.result_repository,
            audit=state.audit_repository,
            tools=state.tool_registry,
            tracer=state.tracer,
            embedding=state.embedding_provider,
            milvus=state.milvus_provider,
            index_execution_mode=state.settings.index_execution_mode,
            index_max_attempts=state.settings.index_max_attempts,
            timeline=state.timeline_repository,
        )

    @staticmethod
    def trace_id() -> str:
        context = get_context()
        return context.trace_id if context else new_id()

    async def review_diagnosis(
        self,
        session_id: str,
        payload: DiagnosisReviewRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisReviewResponse:
        trace_id = self.trace_id()
        with self.tracer.start_span(
            "human.review.submit",
            trace_id=trace_id,
            metadata={"session_id": session_id, "decision": payload.review_result},
        ):
            pass
        session = await self.sessions.get(session_id, trace_id=trace_id)
        result = await self.results.latest(session_id)
        if session is None or result is None:
            raise SessionNotReviewableError("Session has no structured diagnosis result")
        if session.phase not in {DiagnosisPhase.COMPLETED, DiagnosisPhase.NEED_USER_INPUT}:
            raise SessionNotReviewableError("Session is not reviewable")
        valid_evidence = {item.evidence_id for item in result.evidence}
        if any(ref not in valid_evidence for ref in payload.evidence_refs):
            raise InvalidEvidenceReferenceError("Review references unknown evidence")
        candidates = {item.cause for item in result.candidate_causes}
        if (
            payload.review_result == DiagnosisReviewResult.CONFIRMED
            and payload.root_cause not in candidates
            and not payload.override_reason
        ):
            raise RootCauseOverrideReasonRequiredError(
                "Manual root-cause override requires override_reason"
            )
        review_id = new_id()
        fingerprint = request_fingerprint(
            f"diagnosis_review:{session_id}", payload.model_dump(mode="json")
        )
        tool = await ToolExecutor(self.tools, self.tracer).execute(
            "append_case_review",
            {
                "context": {
                    "trace_id": trace_id,
                    "source_system": "energy-agent",
                    "operator_id": actor.actor_id,
                    "actor_role": actor.actor_role,
                    "explicit_human_action": True,
                    "session_id": session_id,
                },
                "session_id": session_id,
                "run_id": result.run_id,
                "review_id": review_id,
                "review_result": payload.review_result,
                "reviewer": actor.actor_id,
                **payload.model_dump(mode="json"),
                "idempotency_key": idempotency_key,
                "request_hash": fingerprint,
            },
            trace_id,
        )
        if not tool.success or not isinstance(tool.data, dict):
            raise DiagnosisReviewInvalidError("Human review could not be recorded")
        review_id = str(tool.data["review_id"])
        case: DiagnosisCase | None = None
        if payload.review_result == DiagnosisReviewResult.CONFIRMED:
            case = await self.cases.get_by_review(review_id)
            if case is None:
                case = await self._create_draft(
                    session_id=session_id,
                    run_id=result.run_id,
                    review_id=review_id,
                    payload=payload,
                    actor=actor,
                    result=result,
                )
        elif payload.review_result == DiagnosisReviewResult.NEEDS_MORE_INFO:
            await self.sessions.update(
                session_id,
                DiagnosisSessionUpdate(
                    phase=DiagnosisPhase.NEED_USER_INPUT,
                    latest_review_status=payload.review_result,
                ),
                trace_id=trace_id,
            )
        else:
            await self.sessions.update(
                session_id,
                DiagnosisSessionUpdate(latest_review_status=payload.review_result),
                trace_id=trace_id,
            )
        action = f"diagnosis.review.{payload.review_result}"
        await self.audit.write(
            actor=actor,
            action=action,
            resource_type="diagnosis",
            resource_id=session_id,
            session_id=session_id,
            case_id=case.case_id if case else None,
            trace_id=trace_id,
            snapshot={
                "review_result": payload.review_result,
                "evidence_refs": payload.evidence_refs,
                "manual_override": bool(payload.override_reason),
            },
        )
        HUMAN_REVIEWS.labels(decision=payload.review_result).inc()
        if self.timeline:
            await self.timeline.append(
                TimelineEventCreate(
                    event_id=timeline_event_id(session_id, "review_submitted", review_id),
                    session_id=session_id,
                    run_id=result.run_id,
                    event_type=TimelineEventType.REVIEW_SUBMITTED,
                    actor_id=actor.actor_id,
                    actor_role=actor.actor_role,
                    payload={
                        "review_id": review_id,
                        "review_result": payload.review_result,
                        "comments": payload.comments or "",
                        "evidence_refs": payload.evidence_refs,
                    },
                )
            )
            if case:
                await self.timeline.append(
                    TimelineEventCreate(
                        event_id=timeline_event_id(session_id, "case_created", case.case_id),
                        session_id=session_id,
                        run_id=result.run_id,
                        event_type=TimelineEventType.CASE_CREATED,
                        actor_id=actor.actor_id,
                        actor_role=actor.actor_role,
                        payload={
                            "case_id": case.case_id,
                            "case_status": case.review_status,
                            "case_version": case.case_version,
                        },
                    )
                )
        return DiagnosisReviewResponse(
            review_id=review_id,
            session_id=session_id,
            run_id=result.run_id,
            review_result=payload.review_result,
            case_id=case.case_id if case else None,
            case_status=case.review_status if case else None,
            trace_id=trace_id,
            created_at=utc_now(),
        )

    async def _create_draft(
        self,
        *,
        session_id: str,
        run_id: str,
        review_id: str,
        payload: DiagnosisReviewRequest,
        actor: ActorContext,
        result: DiagnosisResultRecord,
    ) -> DiagnosisCase:
        with self.tracer.start_span(
            "case.draft.create",
            trace_id=self.trace_id(),
            metadata={"session_id": session_id, "review_id": review_id},
        ):
            pass
        session = await self.sessions.get(session_id, trace_id=self.trace_id())
        assert session is not None and payload.root_cause is not None
        device_evidence = next(
            (item for item in result.evidence if item.source_type == "device"), None
        )
        timeseries = next(
            (item.summary for item in result.evidence if item.source_type == "timeseries"),
            None,
        )
        case = await self.cases.create(
            {
                "case_id": new_id(),
                "source_session_id": session_id,
                "source_run_id": run_id,
                "source_review_id": review_id,
                "source_ticket_id": payload.source_ticket_id,
                "device_type": (
                    device_evidence.metadata.get("device_type") if device_evidence else None
                ),
                "device_model": (
                    device_evidence.metadata.get("device_model") if device_evidence else None
                ),
                "manufacturer": (
                    device_evidence.metadata.get("manufacturer") if device_evidence else None
                ),
                "alarm_name": session.alarm_name,
                "symptom_summary": result.summary,
                "timeseries_features": timeseries,
                "root_cause": payload.root_cause,
                "resolution_steps": payload.resolution_steps,
                "safety_notes": result.safety_notes,
                "evidence_refs": payload.evidence_refs,
                "review_status": CaseStatus.DRAFT,
                "case_version": await self.cases.next_version(session_id),
                "index_status": CaseIndexStatus.PENDING,
                "is_active": False,
                "created_by": actor.actor_id,
            }
        )
        await self.audit.write(
            actor=actor,
            action="case.created",
            resource_type="case",
            resource_id=case.case_id,
            session_id=session_id,
            case_id=case.case_id,
            trace_id=self.trace_id(),
            snapshot={"case_version": case.case_version},
        )
        return case

    async def get(self, case_id: str) -> DiagnosisCase:
        case = await self.cases.get(case_id)
        if case is None:
            raise CaseNotFoundError("Case not found")
        return case

    async def list_cases(self, filters: dict[str, object]) -> list[DiagnosisCase]:
        return await self.cases.list_cases(filters)

    async def list_case_page(
        self, filters: dict[str, object], *, limit: int, cursor: str | None, sort: str
    ) -> tuple[list[DiagnosisCase], int, str | None]:
        return await self.cases.list_page(filters, limit=limit, cursor=cursor, sort=sort)

    async def patch(
        self, case_id: str, payload: CasePatchRequest, actor: ActorContext
    ) -> DiagnosisCase:
        with self.tracer.start_span(
            "case.draft.update",
            trace_id=self.trace_id(),
            metadata={"case_id": case_id},
        ):
            pass
        case = await self.cases.update_draft(
            case_id,
            payload.model_dump(exclude_unset=True),
            actor.actor_id,
            privileged=actor.actor_role in {ActorRole.REVIEWER, ActorRole.ADMIN},
        )
        await self._audit_case(actor, "case.updated", case)
        return case

    async def submit(
        self,
        case_id: str,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        with self.tracer.start_span(
            "case.submit",
            trace_id=self.trace_id(),
            metadata={"case_id": case_id},
        ):
            pass
        case = await self.get(case_id)
        if case.created_by != actor.actor_id and actor.actor_role not in {
            ActorRole.REVIEWER,
            ActorRole.ADMIN,
        }:
            raise CaseNotEditableError("Only creator or reviewer may submit")
        result = await self.results.latest(case.source_session_id)
        valid = {item.evidence_id for item in result.evidence} if result else set()
        missing = missing_case_fields(case, valid)
        if missing:
            raise CaseNotReadyError("Case is incomplete", details={"missing_fields": missing})
        updated = await self.cases.transition(
            case_id,
            expected=CaseStatus.DRAFT,
            target=CaseStatus.PENDING_REVIEW,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            action="case.submitted",
            trace_id=self.trace_id(),
            request_hash=request_fingerprint("case.submit", {"case_id": case_id}),
            idempotency_key=idempotency_key,
        )
        await self._audit_case(actor, "case.submitted", updated)
        return updated

    async def review_case(
        self,
        case_id: str,
        payload: CaseReviewRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        with self.tracer.start_span(
            "case.review",
            trace_id=self.trace_id(),
            metadata={"case_id": case_id, "decision": payload.decision},
        ):
            pass
        case = await self.get(case_id)
        if case.created_by == actor.actor_id:
            raise SelfReviewForbiddenError("Case creator cannot review their own case")
        target = CaseStatus.APPROVED if payload.decision == "approve" else CaseStatus.REJECTED
        index_request = (
            self._index_request(case, IndexOperation.UPSERT)
            if target == CaseStatus.APPROVED and self.index_execution_mode == "rabbitmq"
            else None
        )
        async_updates: dict[str, object] = (
            {"index_status": CaseIndexStatus.QUEUED, "is_active": False} if index_request else {}
        )
        updated = await self.cases.transition(
            case_id,
            expected=CaseStatus.PENDING_REVIEW,
            target=target,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            action="case.approved" if target == CaseStatus.APPROVED else "case.rejected",
            trace_id=self.trace_id(),
            request_hash=request_fingerprint(
                "case.review", {"case_id": case_id, **payload.model_dump(mode="json")}
            ),
            idempotency_key=idempotency_key,
            comment=payload.comment,
            updates={
                "reviewer": actor.actor_id,
                "review_comment": payload.comment,
                **async_updates,
            },
            index_request=index_request,
        )
        if target == CaseStatus.APPROVED:
            if self.index_execution_mode == "sync":
                updated = await self._index(updated, actor, action_prefix="case")
            if updated.index_status == CaseIndexStatus.INDEXED and updated.supersedes_case_id:
                await self._supersede(updated.supersedes_case_id, actor)
        await self._audit_case(
            actor, "case.approved" if target == CaseStatus.APPROVED else "case.rejected", updated
        )
        return updated

    async def disable(
        self,
        case_id: str,
        payload: CaseDisableRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        with self.tracer.start_span(
            "case.disable",
            trace_id=self.trace_id(),
            metadata={"case_id": case_id},
        ):
            pass
        current = await self.get(case_id)
        index_request = (
            self._index_request(current, IndexOperation.TOMBSTONE)
            if self.index_execution_mode == "rabbitmq"
            else None
        )
        case = await self.cases.transition(
            case_id,
            expected=CaseStatus.APPROVED,
            target=CaseStatus.DISABLED,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            action="case.disabled",
            trace_id=self.trace_id(),
            request_hash=request_fingerprint(
                "case.disable", {"case_id": case_id, "reason": payload.reason}
            ),
            idempotency_key=idempotency_key,
            comment=payload.reason,
            updates={
                "is_active": False,
                "index_status": (
                    CaseIndexStatus.QUEUED if index_request else CaseIndexStatus.TOMBSTONED
                ),
            },
            index_request=index_request,
        )
        if self.index_execution_mode == "sync" and self.milvus:
            await self.milvus.delete("case", [case_id])
        await self._audit_case(actor, "case.disabled", case)
        return case

    async def revision(
        self,
        case_id: str,
        payload: CaseRevisionRequest,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        original = await self.get(case_id)
        fingerprint = request_fingerprint(
            "case.revision",
            {"case_id": case_id, **payload.model_dump(mode="json")},
        )
        if idempotency_key:
            event = await self.cases.find_idempotent_event(case_id, idempotency_key)
            if event:
                if event.request_hash != fingerprint:
                    raise CaseStateConflictError("Idempotency key reused with different request")
                if event.comment:
                    existing = await self.cases.get(event.comment)
                    if existing:
                        return existing
        if original.review_status not in {CaseStatus.APPROVED, CaseStatus.REJECTED}:
            raise CaseStateConflictError("Only APPROVED or REJECTED cases can be revised")
        values = original.model_dump(
            exclude={
                "case_id",
                "created_at",
                "updated_at",
                "reviewer",
                "review_comment",
                "embedding_text",
                "index_error_code",
                "index_job_id",
                "graph_projection_status",
            }
        )
        values.update(payload.model_dump(exclude_unset=True, exclude={"submit_for_review"}))
        values.update(
            {
                "case_id": new_id(),
                "case_version": await self.cases.next_version(original.source_session_id),
                "review_status": CaseStatus.DRAFT,
                "index_status": CaseIndexStatus.PENDING,
                "is_active": False,
                "supersedes_case_id": original.case_id,
                "created_by": actor.actor_id,
            }
        )
        revision = await self.cases.create(values)
        await self.cases.append_event(
            case_id=case_id,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            action="case.revision_created",
            from_status=original.review_status,
            to_status=original.review_status,
            comment=revision.case_id,
            idempotency_key=idempotency_key,
            request_hash=fingerprint,
            trace_id=self.trace_id(),
        )
        await self._audit_case(actor, "case.revision_created", revision)
        if payload.submit_for_review:
            revision = await self.submit(revision.case_id, actor, idempotency_key)
        return revision

    async def reindex(
        self,
        case_id: str,
        actor: ActorContext,
        idempotency_key: str | None,
    ) -> DiagnosisCase:
        case = await self.get(case_id)
        fingerprint = request_fingerprint("case.reindex", {"case_id": case_id})
        if idempotency_key:
            event = await self.cases.find_idempotent_event(case_id, idempotency_key)
            if event:
                if event.request_hash != fingerprint:
                    raise CaseStateConflictError("Idempotency key reused with different request")
                return await self.get(case_id)
        if case.review_status != CaseStatus.APPROVED or case.index_status not in {
            CaseIndexStatus.FAILED,
            CaseIndexStatus.PENDING,
            CaseIndexStatus.DEGRADED,
        }:
            raise CaseNotIndexedError("Case is not eligible for reindex")
        if self.index_execution_mode == "rabbitmq":
            updated = await self.cases.queue_index(
                case_id,
                request=self._index_request(case, IndexOperation.REINDEX),
                actor_id=actor.actor_id,
                actor_role=actor.actor_role,
                action="case.reindex_queued",
                trace_id=self.trace_id(),
                request_hash=fingerprint,
                idempotency_key=idempotency_key,
            )
            await self._audit_case(actor, "case.reindex_queued", updated)
            return updated
        await self.cases.append_event(
            case_id=case_id,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            action="case.reindex_started",
            from_status=case.review_status,
            to_status=case.review_status,
            comment=None,
            idempotency_key=idempotency_key,
            request_hash=fingerprint,
            trace_id=self.trace_id(),
        )
        await self._audit_case(actor, "case.reindex_started", case)
        return await self._index(case, actor, action_prefix="case.reindex")

    async def history(self, case_id: str) -> list[CaseReviewEvent]:
        await self.get(case_id)
        return await self.cases.history(case_id)

    async def _index(
        self, case: DiagnosisCase, actor: ActorContext, *, action_prefix: str
    ) -> DiagnosisCase:
        text = build_embedding_text(case)
        try:
            if not self.embedding or not self.milvus:
                raise RuntimeError("case indexing dependencies unavailable")
            with self.tracer.start_span(
                "case.embedding",
                trace_id=self.trace_id(),
                metadata={"case_id": case.case_id, "case_version": case.case_version},
            ):
                vector = (await self.embedding.embed([text]))[0]
            with self.tracer.start_span(
                "case.index",
                trace_id=self.trace_id(),
                metadata={
                    "case_id": case.case_id,
                    "case_version": case.case_version,
                    "dimension": len(vector),
                },
            ):
                await self.milvus.upsert(
                    "case",
                    [
                        {
                            "id": case.case_id,
                            "source_id": case.case_id,
                            "device_type": case.device_type or "",
                            "device_model": case.device_model or "",
                            "manufacturer": case.manufacturer or "",
                            "alarm_name": case.alarm_name or "",
                            "case_version": case.case_version,
                            "verified": True,
                            "effective": True,
                            "index_generation": f"case-v{case.case_version}",
                            "embedding": vector,
                        }
                    ],
                )
            updated = await self.cases.set_index(
                case.case_id,
                CaseIndexStatus.INDEXED,
                embedding_text=text,
                active=True,
            )
            await self._audit_case(actor, f"{action_prefix}_succeeded", updated)
            return updated
        except Exception:
            updated = await self.cases.set_index(
                case.case_id,
                CaseIndexStatus.FAILED,
                error_code="CASE_INDEX_PROVIDER_FAILED",
                embedding_text=text,
                active=False,
            )
            await self._audit_case(actor, f"{action_prefix}_failed", updated)
            return updated

    async def _supersede(self, case_id: str, actor: ActorContext) -> None:
        with self.tracer.start_span(
            "case.supersede",
            trace_id=self.trace_id(),
            metadata={"case_id": case_id},
        ):
            pass
        current = await self.get(case_id)
        index_request = (
            self._index_request(current, IndexOperation.TOMBSTONE)
            if self.index_execution_mode == "rabbitmq"
            else None
        )
        old = await self.cases.transition(
            case_id,
            expected=CaseStatus.APPROVED,
            target=CaseStatus.SUPERSEDED,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            action="case.superseded",
            trace_id=self.trace_id(),
            request_hash=request_fingerprint("case.supersede", {"case_id": case_id}),
            idempotency_key=f"supersede:{case_id}",
            updates={
                "is_active": False,
                "index_status": (
                    CaseIndexStatus.QUEUED if index_request else CaseIndexStatus.TOMBSTONED
                ),
            },
            index_request=index_request,
        )
        if self.index_execution_mode == "sync" and self.milvus:
            await self.milvus.delete("case", [case_id])
        await self._audit_case(actor, "case.superseded", old)

    def _index_request(self, case: DiagnosisCase, operation: IndexOperation) -> IndexJobCreate:
        trace_id = self.trace_id()
        return IndexJobCreate(
            entity_type=EntityType.DIAGNOSIS_CASE,
            entity_id=case.case_id,
            entity_version=str(case.case_version),
            operation=operation,
            trace_id=trace_id,
            correlation_id=case.source_session_id,
            causation_id=case.source_review_id,
            max_attempts=self.index_max_attempts,
        )

    async def _audit_case(self, actor: ActorContext, action: str, case: DiagnosisCase) -> None:
        await self.audit.write(
            actor=actor,
            action=action,
            resource_type="case",
            resource_id=case.case_id,
            session_id=case.source_session_id,
            case_id=case.case_id,
            trace_id=self.trace_id(),
            snapshot={
                "status": case.review_status,
                "index_status": case.index_status,
                "case_version": case.case_version,
            },
        )
