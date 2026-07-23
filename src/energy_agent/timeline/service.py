from energy_agent.core.context import ActorContext
from energy_agent.core.errors import ResourceNotFoundError
from energy_agent.timeline.contracts import (
    TimelineEventCreate,
    TimelineEventType,
    TimelineItem,
    TimelineResponse,
    timeline_event_id,
)
from energy_agent.timeline.ports import (
    TimelineCasePort,
    TimelineRepositoryPort,
    TimelineResultPort,
    TimelineReviewPort,
    TimelineSessionPort,
    TimelineStepPort,
)


class TimelineService:
    def __init__(
        self,
        repository: TimelineRepositoryPort,
        sessions: TimelineSessionPort,
        steps: TimelineStepPort,
        results: TimelineResultPort,
        reviews: TimelineReviewPort,
        cases: TimelineCasePort,
    ) -> None:
        self.repository = repository
        self.sessions = sessions
        self.steps = steps
        self.results = results
        self.reviews = reviews
        self.cases = cases

    def create(
        self,
        session_id: str,
        event_type: TimelineEventType,
        key: str,
        *,
        run_id: str | None = None,
        actor: ActorContext | None = None,
        payload: dict[str, object] | None = None,
    ) -> TimelineEventCreate:
        return TimelineEventCreate(
            event_id=timeline_event_id(session_id, event_type, key),
            session_id=session_id,
            run_id=run_id,
            event_type=event_type,
            actor_id=actor.actor_id if actor else None,
            actor_role=actor.actor_role if actor else None,
            payload=payload or {},
        )

    async def append(
        self,
        session_id: str,
        event_type: TimelineEventType,
        key: str,
        *,
        run_id: str | None = None,
        actor: ActorContext | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        await self.repository.append(
            self.create(
                session_id,
                event_type,
                key,
                run_id=run_id,
                actor=actor,
                payload=payload,
            )
        )

    async def get(self, session_id: str) -> TimelineResponse:
        session = await self.sessions.get(session_id, trace_id="timeline-query")
        if not session:
            raise ResourceNotFoundError("Diagnosis session not found")
        events = await self.repository.list(session_id)
        steps = await self.steps.list_by_session(session_id, trace_id=session.trace_id)
        latest_result = await self.results.latest(session_id)
        reviews = await self.reviews.list_by_session(session_id)
        cases = await self.cases.list_by_session(session_id)
        items: list[TimelineItem] = []
        event_kind = {
            TimelineEventType.REVIEW_SUBMITTED: "review",
            TimelineEventType.CASE_CREATED: "case_event",
        }
        for event in events:
            items.append(
                TimelineItem(
                    timeline_id=event.event_id,
                    sequence=event.sequence * 100,
                    kind=event_kind.get(event.event_type, event.event_type),
                    run_id=event.run_id,
                    timestamp=event.created_at,
                    payload=event.payload,
                )
            )
        for index, step in enumerate(steps, start=1):
            kind = "tool_result" if step.step_name.startswith("tool.") else "agent_progress"
            if step.step_status == "FAILED":
                kind = "error"
            items.append(
                TimelineItem(
                    timeline_id=f"step:{step.id}",
                    sequence=index * 100 + 50,
                    kind=kind,
                    run_id=step.run_id,
                    timestamp=step.started_at,
                    status=step.step_status,
                    title=step.step_name,
                    payload={
                        "output": step.output_snapshot or {},
                        "error_code": step.error_code or "",
                    },
                )
            )
        persisted_result_runs = {
            event.run_id
            for event in events
            if event.event_type == TimelineEventType.DIAGNOSIS_RESULT
        }
        if latest_result and latest_result.run_id not in persisted_result_runs:
            items.append(
                TimelineItem(
                    timeline_id=f"result:{latest_result.run_id}",
                    sequence=0,
                    kind="diagnosis_result",
                    run_id=latest_result.run_id,
                    timestamp=latest_result.created_at,
                    payload={
                        "summary": latest_result.summary,
                        "risk_level": latest_result.risk_level,
                        "evidence_refs": [
                            evidence.evidence_id for evidence in latest_result.evidence
                        ],
                    },
                )
            )
        persisted_review_ids = {
            str(event.payload.get("review_id"))
            for event in events
            if event.event_type == TimelineEventType.REVIEW_SUBMITTED
        }
        for review in reviews:
            if review.review_id in persisted_review_ids:
                continue
            items.append(
                TimelineItem(
                    timeline_id=f"review:{review.review_id}",
                    sequence=0,
                    kind="review",
                    run_id=review.run_id,
                    timestamp=review.created_at,
                    payload={
                        "review_id": review.review_id,
                        "review_result": review.review_result,
                        "comments": review.comments or "",
                        "evidence_refs": review.evidence_refs,
                    },
                )
            )
        persisted_case_ids = {
            str(event.payload.get("case_id"))
            for event in events
            if event.event_type == TimelineEventType.CASE_CREATED
        }
        for case in cases:
            if case.case_id in persisted_case_ids:
                continue
            items.append(
                TimelineItem(
                    timeline_id=f"case:{case.case_id}",
                    sequence=0,
                    kind="case_event",
                    run_id=case.source_run_id,
                    timestamp=case.created_at,
                    payload={
                        "case_id": case.case_id,
                        "case_status": case.review_status,
                        "case_version": case.case_version,
                    },
                )
            )
        items.sort(key=lambda item: (item.timestamp, item.sequence, item.timeline_id))
        normalized = [
            item.model_copy(update={"sequence": index}) for index, item in enumerate(items, start=1)
        ]
        return TimelineResponse(
            session_id=session_id,
            history_complete=any(
                event.event_type == TimelineEventType.USER_MESSAGE for event in events
            ),
            items=normalized,
        )
