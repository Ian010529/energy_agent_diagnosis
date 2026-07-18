from fastapi import Request

from energy_agent.agent.state import (
    AlarmContext,
    DeviceContext,
    DiagnosisState,
    UserFeedback,
)
from energy_agent.agent.workflow import build_diagnosis_graph
from energy_agent.contracts.common import DiagnosisIntent, DiagnosisPhase
from energy_agent.contracts.diagnosis import (
    CreateSessionRequest,
    CreateSessionResponse,
    DiagnosisChatRequest,
    DiagnosisResponse,
    DiagnosisResultCreate,
    DiagnosisRunCreate,
    DiagnosisSessionCreate,
    DiagnosisSessionUpdate,
    SessionMemoryPayload,
    StepLogCreate,
    StructuredDiagnosisResult,
)
from energy_agent.core.context import ActorContext, get_context
from energy_agent.core.errors import (
    ClarificationAlreadyAnsweredError,
    ClarificationStaleError,
    ConflictError,
    IdempotencyConflictError,
    ResourceNotFoundError,
    UnknownClarificationQuestionError,
)
from energy_agent.core.idempotency import request_fingerprint
from energy_agent.core.ids import new_id
from energy_agent.core.time import utc_now
from energy_agent.memory.session_store import RedisSessionStore
from energy_agent.model.gateway import ModelGateway
from energy_agent.observability.tracing import Tracer
from energy_agent.persistence.repositories.audit import AuditRepository
from energy_agent.persistence.repositories.diagnosis_run import (
    DiagnosisResultRepository,
    DiagnosisRunRepository,
)
from energy_agent.persistence.repositories.diagnosis_session import (
    DiagnosisSessionRepository,
)
from energy_agent.persistence.repositories.diagnosis_step_log import (
    DiagnosisStepLogRepository,
)
from energy_agent.tools.executor import ToolExecutor
from energy_agent.tools.registry import ToolRegistry


class DiagnosisService:
    def __init__(
        self,
        *,
        sessions: DiagnosisSessionRepository,
        runs: DiagnosisRunRepository,
        results: DiagnosisResultRepository,
        step_logs: DiagnosisStepLogRepository,
        memory: RedisSessionStore,
        tools: ToolRegistry,
        tracer: Tracer,
        model_gateway: ModelGateway | None = None,
        audit: AuditRepository | None = None,
    ) -> None:
        self.sessions = sessions
        self.runs = runs
        self.results = results
        self.step_logs = step_logs
        self.memory = memory
        self.tools = tools
        self.tracer = tracer
        self.model_gateway = model_gateway
        self.audit = audit

    @classmethod
    def from_request(cls, request: Request) -> "DiagnosisService":
        state = request.app.state
        return cls(
            sessions=state.session_repository,
            runs=state.run_repository,
            results=state.result_repository,
            step_logs=state.step_log_repository,
            memory=state.session_store,
            tools=state.tool_registry,
            tracer=state.tracer,
            model_gateway=state.model_gateway,
            audit=state.audit_repository,
        )

    @staticmethod
    def _trace_id() -> str:
        context = get_context()
        return context.trace_id if context else new_id()

    async def create_session(
        self,
        payload: CreateSessionRequest,
        idempotency_key: str | None,
        actor: ActorContext | None = None,
    ) -> CreateSessionResponse:
        trace_id = self._trace_id()
        session_id, run_id = new_id(), new_id()
        fingerprint = request_fingerprint("create_session", payload.model_dump(mode="json"))
        if idempotency_key:
            existing = await self.runs.find_idempotent_global(idempotency_key, trace_id=trace_id)
            if existing:
                if existing.request_hash != fingerprint:
                    raise IdempotencyConflictError("Idempotency key reused with different request")
                existing_session = await self.sessions.get(existing.session_id, trace_id=trace_id)
                assert existing_session is not None
                return CreateSessionResponse(
                    session_id=existing.session_id,
                    run_id=existing.id,
                    phase=existing_session.phase,
                    trace_id=existing.trace_id,
                )
        await self.sessions.create(
            DiagnosisSessionCreate(
                id=session_id,
                source=payload.source,
                site_id=payload.site_id,
                device_id=payload.device_id,
                alarm_id=payload.alarm_id,
                alarm_name=payload.alarm_name,
                trace_id=trace_id,
                run_id=run_id,
                created_by=actor.actor_id if actor else None,
            )
        )
        await self.runs.create(
            DiagnosisRunCreate(
                id=run_id,
                session_id=session_id,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                request_hash=fingerprint,
            )
        )
        await self.memory.save(
            SessionMemoryPayload(
                session_id=session_id,
                phase=DiagnosisPhase.INIT,
                run_id=run_id,
                trace_id=trace_id,
                updated_at=utc_now(),
                device_context={
                    key: value
                    for key, value in {
                        "site_id": payload.site_id,
                        "device_id": payload.device_id,
                    }.items()
                    if value is not None
                }
                or None,
                alarm_context={
                    key: value
                    for key, value in {
                        "alarm_id": payload.alarm_id,
                        "alarm_name": payload.alarm_name,
                    }.items()
                    if value is not None
                }
                or None,
            )
        )
        if actor and self.audit:
            await self.audit.write(
                actor=actor,
                action="diagnosis.created",
                resource_type="diagnosis",
                resource_id=session_id,
                session_id=session_id,
                trace_id=trace_id,
                snapshot={"source": payload.source, "device_id": payload.device_id},
            )
        return CreateSessionResponse(
            session_id=session_id,
            run_id=run_id,
            phase=DiagnosisPhase.INIT,
            trace_id=trace_id,
        )

    async def diagnose(
        self,
        payload: DiagnosisChatRequest,
        idempotency_key: str | None = None,
        actor: ActorContext | None = None,
    ) -> DiagnosisResponse:
        trace_id = self._trace_id()
        session = await self.sessions.get(payload.session_id, trace_id=trace_id)
        if session is None:
            raise ResourceNotFoundError(f"Diagnosis session {payload.session_id} not found")
        fingerprint = request_fingerprint(
            f"chat:{payload.session_id}", payload.model_dump(mode="json")
        )
        if idempotency_key:
            existing = await self.runs.find_idempotent(
                payload.session_id, idempotency_key, trace_id=trace_id
            )
            if existing:
                if existing.request_hash != fingerprint:
                    raise IdempotencyConflictError("Idempotency key reused with different request")
                return await self.get_session(payload.session_id)
        if session.phase == DiagnosisPhase.FAILED:
            raise ConflictError(f"Session is terminal: {session.phase}")
        if payload.clarification_answers or payload.followup_mode:
            with self.tracer.start_span(
                "human.clarification.restore",
                trace_id=trace_id,
                metadata={"session_id": payload.session_id},
            ):
                memory = await self.memory.get(payload.session_id, trace_id=trace_id)
        else:
            memory = await self.memory.get(payload.session_id, trace_id=trace_id)
        mode = payload.followup_mode or (
            "answer_clarification" if payload.clarification_answers else "new_information"
        )
        if session.phase == DiagnosisPhase.COMPLETED:
            if mode != "explain_previous_result":
                raise ConflictError(f"Session is terminal: {session.phase}")
            return await self._explain_previous(
                session_id=payload.session_id,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                memory=memory,
            )
        if payload.clarification_answers:
            with self.tracer.start_span(
                "human.clarification.apply",
                trace_id=trace_id,
                metadata={
                    "session_id": payload.session_id,
                    "question_ids": [item.question_id for item in payload.clarification_answers],
                },
            ):
                pass
            if memory is None:
                raise ConflictError("Clarification context is unavailable")
            if (
                payload.expected_memory_revision is not None
                and payload.expected_memory_revision != memory.memory_revision
            ):
                raise ClarificationStaleError("Clarification memory revision is stale")
            pending = set(memory.pending_question_ids)
            if not pending:
                pending = {item.question_id for item in memory.clarification_questions}
            resolved = set(memory.resolved_question_ids)
            seen: set[str] = set()
            for answer in payload.clarification_answers:
                if not answer.answer.strip():
                    raise UnknownClarificationQuestionError("Clarification answer is empty")
                if answer.question_id in resolved or answer.question_id in seen:
                    raise ClarificationAlreadyAnsweredError(
                        f"Question {answer.question_id} was already answered"
                    )
                if answer.question_id not in pending:
                    raise UnknownClarificationQuestionError(
                        f"Unknown clarification question {answer.question_id}"
                    )
                seen.add(answer.question_id)

        run_id = new_id()
        await self.runs.create(
            DiagnosisRunCreate(
                id=run_id,
                session_id=payload.session_id,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                request_hash=fingerprint,
                parent_run_id=memory.run_id if memory else session.run_id,
                run_type="clarification" if payload.clarification_answers else "diagnosis",
            )
        )
        feedback = [
            *(
                [
                    UserFeedback(question_id=item.question_id, answer=item.answer)
                    for item in memory.user_feedback_history
                ]
                if memory
                else []
            ),
            *[
                UserFeedback(question_id=item.question_id, answer=item.answer)
                for item in payload.clarification_answers
            ],
        ]
        initial = DiagnosisState(
            session_id=payload.session_id,
            run_id=run_id,
            trace_id=trace_id,
            source=session.source,
            user_message=payload.message,
            followup_mode=mode,
            memory_revision=(memory.memory_revision + 1 if memory else 1),
            parent_run_id=memory.run_id if memory else session.run_id,
            device_context=(
                DeviceContext.model_validate(memory.device_context)
                if memory and memory.device_context
                else DeviceContext(site_id=session.site_id, device_id=session.device_id)
                if session.device_id
                else None
            ),
            alarm_context=(
                AlarmContext.model_validate(memory.alarm_context)
                if memory and memory.alarm_context
                else AlarmContext(alarm_id=session.alarm_id, alarm_name=session.alarm_name or "")
                if session.alarm_id
                else None
            ),
            diagnosis_template_id=memory.diagnosis_template_id if memory else None,
            plan=memory.plan if memory else [],
            tool_results=(
                [
                    {
                        "tool_name": str(item.get("tool_name", "")),
                        "status": str(item.get("status", "OK")),
                        "result_ref": item.get("result_ref"),
                        "summary": item.get("summary"),
                    }
                    for item in memory.tool_summaries
                ]
                if memory
                else []
            ),
            evidence=memory.evidence if memory else [],
            evidence_refs=memory.evidence_refs if memory else [],
            candidate_causes=memory.candidate_causes if memory else [],
            degraded_components=memory.degraded_components if memory else [],
            user_feedback=feedback,
        )

        async def log_step(
            state: DiagnosisState,
            name: str,
            output: dict[str, object] | None,
            error: BaseException | None,
        ) -> None:
            now = utc_now()
            await self.step_logs.create(
                StepLogCreate(
                    session_id=state.session_id,
                    run_id=state.run_id,
                    trace_id=state.trace_id,
                    step_name=f"agent.{name}",
                    step_status="FAILED" if error else "OK",
                    output_snapshot=output,
                    error_code=type(error).__name__ if error else None,
                    started_at=now,
                    ended_at=now,
                    duration_ms=0,
                )
            )

        async def write_memory(state: DiagnosisState) -> None:
            if state.final_response:
                result = StructuredDiagnosisResult.model_validate(state.final_response)
                await self.results.upsert(
                    DiagnosisResultCreate(
                        run_id=state.run_id,
                        session_id=state.session_id,
                        **result.model_dump(),
                    )
                )

        executor = ToolExecutor(self.tools, self.tracer)
        graph = build_diagnosis_graph(
            executor,
            self.tracer,
            memory_writer=write_memory,
            step_logger=log_step,
            model_gateway=self.model_gateway,
        )
        with self.tracer.start_span(
            "diagnosis.workflow",
            trace_id=trace_id,
            metadata={"session_id": payload.session_id, "run_id": run_id},
        ):
            output = await graph.ainvoke(initial)
        state = DiagnosisState.model_validate(output)
        for summary in state.tool_results:
            now = utc_now()
            await self.step_logs.create(
                StepLogCreate(
                    session_id=state.session_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    step_name=f"tool.{summary.tool_name}",
                    step_status=summary.status,
                    output_snapshot=summary.model_dump(),
                    started_at=now,
                    ended_at=now,
                    duration_ms=0,
                )
            )
        status = "completed" if state.phase == DiagnosisPhase.COMPLETED else "waiting_input"
        await self.runs.finish(run_id, state.phase, status)
        result = (
            StructuredDiagnosisResult.model_validate(state.final_response)
            if state.final_response
            else None
        )
        session_updates: dict[str, object] = {
            "phase": state.phase,
            "run_id": run_id,
        }
        if result:
            session_updates.update(
                final_summary=result.summary,
                risk_level=result.risk_level,
            )
        await self.sessions.update(
            payload.session_id,
            DiagnosisSessionUpdate.model_validate(session_updates),
            trace_id=trace_id,
        )
        await self.memory.save(self._memory_payload(state, result))
        if actor and self.audit and payload.clarification_answers:
            await self.audit.write(
                actor=actor,
                action="clarification.submitted",
                resource_type="diagnosis",
                resource_id=payload.session_id,
                session_id=payload.session_id,
                trace_id=trace_id,
                snapshot={
                    "question_ids": [item.question_id for item in payload.clarification_answers],
                    "answer_lengths": [len(item.answer) for item in payload.clarification_answers],
                },
            )
        return self._response(state, result)

    def _memory_payload(
        self, state: DiagnosisState, result: StructuredDiagnosisResult | None
    ) -> SessionMemoryPayload:
        resolved = [item.question_id for item in state.user_feedback]
        return SessionMemoryPayload(
            session_id=state.session_id,
            phase=state.phase,
            run_id=state.run_id,
            trace_id=state.trace_id,
            updated_at=utc_now(),
            device_context=state.device_context.model_dump(mode="json")
            if state.device_context
            else None,
            alarm_context=state.alarm_context.model_dump(mode="json")
            if state.alarm_context
            else None,
            intent=state.intent,
            diagnosis_template_id=state.diagnosis_template_id,
            plan=state.plan,
            tool_summaries=[item.model_dump(mode="json") for item in state.tool_results],
            evidence=state.evidence,
            evidence_refs=state.evidence_refs,
            candidate_causes=state.candidate_causes,
            clarification_questions=state.clarification_questions,
            clarification_answers=[
                {"question_id": item.question_id, "answer": item.answer}
                for item in state.user_feedback
            ],
            final_result=result,
            degraded_components=state.degraded_components,
            prompt_version=state.prompt_version,
            final_summary=result.summary if result else None,
            risk_level=result.risk_level if result else state.risk_level,
            memory_revision=state.memory_revision,
            parent_run_id=state.parent_run_id,
            time_window=state.time_window.model_dump(mode="json") if state.time_window else None,
            pending_question_ids=[
                item.question_id
                for item in state.clarification_questions
                if item.question_id not in resolved
            ],
            resolved_question_ids=resolved,
            user_feedback_history=[
                {"question_id": item.question_id, "answer": item.answer}
                for item in state.user_feedback
            ],
            evidence_package_ids=sorted(
                {item.package_id for item in state.evidence if item.package_id}
            ),
            last_completed_node=(
                "memory_writer"
                if state.phase == DiagnosisPhase.COMPLETED
                else "clarification_generator"
            ),
        )

    @staticmethod
    def _response(
        state: DiagnosisState, result: StructuredDiagnosisResult | None
    ) -> DiagnosisResponse:
        return DiagnosisResponse(
            session_id=state.session_id,
            run_id=state.run_id,
            trace_id=state.trace_id,
            phase=state.phase,
            intent=state.intent,
            result=result,
            evidence_refs=state.evidence_refs,
            tool_summaries=[item.model_dump(mode="json") for item in state.tool_results],
            clarification_questions=state.clarification_questions,
            degraded_components=state.degraded_components,
            memory_revision=state.memory_revision,
        )

    async def get_session(self, session_id: str) -> DiagnosisResponse:
        trace_id = self._trace_id()
        session = await self.sessions.get(session_id, trace_id=trace_id)
        if session is None:
            raise ResourceNotFoundError(f"Diagnosis session {session_id} not found")
        memory = await self.memory.get(session_id, trace_id=trace_id)
        if memory:
            return DiagnosisResponse(
                session_id=session_id,
                run_id=memory.run_id,
                trace_id=memory.trace_id,
                phase=memory.phase,
                intent=memory.intent,
                result=memory.final_result,
                evidence_refs=memory.evidence_refs,
                tool_summaries=memory.tool_summaries,
                clarification_questions=memory.clarification_questions,
                degraded_components=memory.degraded_components,
                memory_revision=memory.memory_revision,
            )
        run = await self.runs.latest(session_id, trace_id=trace_id)
        result = await self.results.latest(session_id)
        return DiagnosisResponse(
            session_id=session_id,
            run_id=run.id if run else session.run_id,
            trace_id=run.trace_id if run else session.trace_id,
            phase=session.phase,
            result=(
                StructuredDiagnosisResult.model_validate(
                    result.model_dump(exclude={"run_id", "session_id", "created_at", "updated_at"})
                )
                if result
                else None
            ),
            evidence_refs=[item.evidence_id for item in result.evidence] if result else [],
            degraded_components=result.degraded_components if result else [],
        )

    async def _explain_previous(
        self,
        *,
        session_id: str,
        trace_id: str,
        idempotency_key: str | None,
        fingerprint: str,
        memory: SessionMemoryPayload | None,
    ) -> DiagnosisResponse:
        result = memory.final_result if memory else None
        if result is None:
            persisted = await self.results.latest(session_id)
            if persisted:
                result = StructuredDiagnosisResult.model_validate(
                    persisted.model_dump(
                        exclude={"run_id", "session_id", "created_at", "updated_at"}
                    )
                )
        if result is None:
            raise ConflictError("Completed session has no result to explain")
        latest = await self.runs.latest(session_id, trace_id=trace_id)
        parent = memory.run_id if memory else latest.id if latest else ""
        run_id = new_id()
        await self.runs.create(
            DiagnosisRunCreate(
                id=run_id,
                session_id=session_id,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                request_hash=fingerprint,
                phase=DiagnosisPhase.COMPLETED,
                parent_run_id=parent,
                run_type="explanation",
            )
        )
        await self.runs.finish(run_id, DiagnosisPhase.COMPLETED, "completed")
        with self.tracer.start_span(
            "human.explanation",
            trace_id=trace_id,
            metadata={"session_id": session_id, "parent_run_id": parent},
        ):
            pass
        return DiagnosisResponse(
            session_id=session_id,
            run_id=run_id,
            trace_id=trace_id,
            phase=DiagnosisPhase.COMPLETED,
            intent=DiagnosisIntent.FOLLOWUP_CLARIFICATION,
            result=result,
            evidence_refs=[item.evidence_id for item in result.evidence],
            memory_revision=memory.memory_revision if memory else None,
        )
