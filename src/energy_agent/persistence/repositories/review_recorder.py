from energy_agent.cases.review_recorder import ReviewRecord
from energy_agent.persistence.repositories.diagnosis_review import DiagnosisReviewRepository
from energy_agent.tools.contracts import AppendCaseReviewInput


class RepositoryDiagnosisReviewRecorder:
    def __init__(self, reviews: DiagnosisReviewRepository) -> None:
        self.reviews = reviews

    async def append(self, request: AppendCaseReviewInput) -> ReviewRecord:
        model = await self.reviews.append(
            {
                "review_id": request.review_id,
                "session_id": request.session_id,
                "run_id": request.run_id,
                "actor_id": request.context.operator_id,
                "actor_role": request.context.actor_role,
                "review_result": request.review_result,
                "root_cause": request.root_cause,
                "resolution_steps": request.resolution_steps,
                "comments": request.comments or request.review_comment,
                "evidence_refs": request.evidence_refs,
                "source_ticket_id": request.source_ticket_id,
                "override_reason": request.override_reason,
                "requested_questions": request.requested_questions,
                "idempotency_key": request.idempotency_key,
                "request_hash": request.request_hash,
                "trace_id": request.context.trace_id,
            }
        )
        return ReviewRecord(model.review_id, self.reviews.created_at(model))
