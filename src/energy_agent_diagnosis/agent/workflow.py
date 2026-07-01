"""阶段 4 LangGraph 诊断工作流。"""

from collections.abc import Awaitable, Callable
from typing import Any, NotRequired, TypedDict, cast

from langgraph.graph import END, StateGraph

from energy_agent_diagnosis.contracts import (
    AlarmContext,
    CandidateCause,
    DiagnosisResult,
    DiagnosisStateEvent,
    DiagnosisStatus,
    EvidencePackage,
    RequestContext,
    TicketSuggestion,
    ToolCallSummary,
    ToolContext,
    ToolMeta,
    ToolResult,
    ToolStatus,
    utc_now,
)
from energy_agent_diagnosis.ports.providers import Payload, ProviderLookup, ProviderResult
from energy_agent_diagnosis.retrieval import retrieve_evidence
from energy_agent_diagnosis.tools import (
    get_alarm_detail,
    get_device_profile,
    query_timeseries_window,
)


class AgentWorkflowState(TypedDict):
    """LangGraph 节点间传递的阶段 4 状态。"""

    request_context: RequestContext
    status: DiagnosisStatus
    events: list[DiagnosisStateEvent]
    tool_calls: list[ToolCallSummary]
    plan: list[str]
    evidence_package: NotRequired[EvidencePackage | None]
    result: NotRequired[DiagnosisResult | None]
    clarification_answer: NotRequired[str | None]
    failure_reason: NotRequired[str | None]


ToolFunction = Callable[[ProviderLookup, ToolContext, Payload], Awaitable[ProviderResult]]


class DiagnosisWorkflow:
    """把文档要求的 Agent 节点落地为 LangGraph 可执行图。"""

    def __init__(self, *, registry: ProviderLookup, settings: Any) -> None:
        """绑定 Provider 注册表和运行期配置。"""
        self._registry = registry
        self._settings = settings
        self._graph = self._build_graph()

    async def run(
        self,
        *,
        request_context: RequestContext,
        existing_events: list[DiagnosisStateEvent] | None = None,
        existing_tool_calls: list[ToolCallSummary] | None = None,
        clarification_answer: str | None = None,
    ) -> AgentWorkflowState:
        """执行或恢复一次诊断图。"""
        initial_state: AgentWorkflowState = {
            "request_context": request_context,
            "status": DiagnosisStatus.INIT,
            "events": list(existing_events or []),
            "tool_calls": list(existing_tool_calls or []),
            "plan": [],
            "evidence_package": None,
            "result": None,
            "clarification_answer": clarification_answer,
        }
        return cast(AgentWorkflowState, await self._graph.ainvoke(initial_state))

    def _build_graph(self) -> Any:
        workflow = StateGraph(AgentWorkflowState)
        workflow.add_node("intent_router", self._intent_router)
        workflow.add_node("entity_parser", self._entity_parser)
        workflow.add_node("plan_builder", self._plan_builder)
        workflow.add_node("tool_dispatcher", self._tool_dispatcher)
        workflow.add_node("evidence_aggregator", self._evidence_aggregator)
        workflow.add_node("gap_detector", self._gap_detector)
        workflow.add_node("clarification_generator", self._clarification_generator)
        workflow.add_node("reason_generator", self._reason_generator)
        workflow.add_node("response_generator", self._response_generator)
        workflow.add_node("rule_checker", self._rule_checker)

        workflow.set_entry_point("intent_router")
        workflow.add_edge("intent_router", "entity_parser")
        workflow.add_edge("entity_parser", "plan_builder")
        workflow.add_edge("plan_builder", "tool_dispatcher")
        workflow.add_edge("tool_dispatcher", "evidence_aggregator")
        workflow.add_edge("evidence_aggregator", "gap_detector")
        workflow.add_conditional_edges(
            "gap_detector",
            self._route_after_gap_detection,
            {
                "clarify": "clarification_generator",
                "reason": "reason_generator",
                "failed": END,
            },
        )
        workflow.add_edge("clarification_generator", END)
        workflow.add_edge("reason_generator", "response_generator")
        workflow.add_edge("response_generator", "rule_checker")
        workflow.add_edge("rule_checker", END)
        return workflow.compile()

    async def _intent_router(self, state: AgentWorkflowState) -> AgentWorkflowState:
        request = state["request_context"]
        intent = "fault_diagnosis" if request.alarm or request.device_id else "knowledge_qa"
        state["status"] = DiagnosisStatus.INIT
        _append_event(state, "intent_routed", "已识别诊断意图", 10, {"intent": intent})
        return state

    async def _entity_parser(self, state: AgentWorkflowState) -> AgentWorkflowState:
        request = state["request_context"]
        context = _tool_context(request)

        if request.alarm and request.alarm.alarm_id:
            result = await self._safe_tool_call(
                state,
                "get_alarm_detail",
                get_alarm_detail,
                context,
                {"alarm_id": request.alarm.alarm_id},
            )
            if result.success and result.data:
                data = result.data
                alarm = AlarmContext.model_validate(data)
                request = request.model_copy(
                    update={
                        "alarm": alarm,
                        "device_id": request.device_id or _optional_str(data.get("device_id")),
                        "site_id": request.site_id or _optional_str(data.get("site_id")),
                    }
                )

        if request.device_id:
            result = await self._safe_tool_call(
                state,
                "get_device_profile",
                get_device_profile,
                context,
                {"device_id": request.device_id},
            )
            if result.success and result.data:
                data = result.data
                request = request.model_copy(
                    update={
                        "device_type": request.device_type
                        or _optional_str(data.get("device_type")),
                        "device_model": request.device_model
                        or _optional_str(data.get("device_model")),
                        "manufacturer": request.manufacturer
                        or _optional_str(data.get("manufacturer")),
                        "site_id": request.site_id or _optional_str(data.get("site_id")),
                    }
                )

        state["request_context"] = request
        _append_event(
            state,
            "entity_parsed",
            "已解析设备、场站和告警实体",
            20,
            {
                "device_id": request.device_id,
                "alarm_name": request.alarm.alarm_name if request.alarm else None,
            },
        )
        return state

    async def _plan_builder(self, state: AgentWorkflowState) -> AgentWorkflowState:
        request = state["request_context"]
        alarm_name = request.alarm.alarm_name if request.alarm else ""
        state["status"] = DiagnosisStatus.PLAN_READY
        state["plan"] = [
            "核对告警与设备画像",
            "查询时序窗口摘要",
            "检索手册、历史工单和图谱关系",
            "归并证据并生成候选根因",
            "执行规则校验并输出排查建议",
        ]
        _append_event(
            state,
            "plan_ready",
            "已生成诊断计划",
            30,
            {"alarm_name": alarm_name, "steps": state["plan"]},
        )
        return state

    async def _tool_dispatcher(self, state: AgentWorkflowState) -> AgentWorkflowState:
        request = state["request_context"]
        state["status"] = DiagnosisStatus.DATA_FETCHING
        if request.device_id and request.alarm and request.alarm.trigger_time:
            await self._safe_tool_call(
                state,
                "query_timeseries_window",
                query_timeseries_window,
                _tool_context(request),
                {
                    "device_id": request.device_id,
                    "metrics": [],
                    "start_time": request.alarm.trigger_time.isoformat(),
                    "end_time": request.alarm.trigger_time.isoformat(),
                },
            )
        _append_event(
            state,
            "tool_dispatch_completed",
            "已完成结构化工具调度",
            45,
            {"tool_count": len(state["tool_calls"])},
        )
        return state

    async def _evidence_aggregator(self, state: AgentWorkflowState) -> AgentWorkflowState:
        request = state["request_context"]
        try:
            package = await retrieve_evidence(
                self._registry,
                _tool_context(request),
                request,
                self._settings,
            )
        except Exception as exc:
            state["status"] = DiagnosisStatus.FAILED
            state["failure_reason"] = type(exc).__name__
            _append_event(
                state,
                "retrieval_failed",
                "证据检索失败，建议人工接管",
                55,
                {"error_type": type(exc).__name__},
            )
            return state

        state["status"] = DiagnosisStatus.EVIDENCE_READY
        state["evidence_package"] = package
        _append_event(
            state,
            "retrieval_completed",
            "已完成手册、历史工单、图谱和时序证据归并",
            65,
            {
                "evidence_count": len(package.ranked_evidence),
                "degraded_sources": package.degraded_sources,
            },
        )
        return state

    async def _gap_detector(self, state: AgentWorkflowState) -> AgentWorkflowState:
        package = state.get("evidence_package")
        if package is None:
            state["status"] = DiagnosisStatus.FAILED
            state["failure_reason"] = "EVIDENCE_PACKAGE_MISSING"
            return state
        if package.need_manual_confirmation and not state.get("clarification_answer"):
            state["status"] = DiagnosisStatus.NEED_USER_INPUT
            _append_event(
                state,
                "need_user_input",
                "关键证据不足，需要补充现场信息",
                70,
                {"degraded_sources": package.degraded_sources},
            )
            return state
        _append_event(state, "gap_checked", "证据满足生成候选结论的最低要求", 72, {})
        return state

    async def _clarification_generator(self, state: AgentWorkflowState) -> AgentWorkflowState:
        request = state["request_context"]
        package = state.get("evidence_package")
        result = DiagnosisResult(
            session_id=request.session_id,
            status=DiagnosisStatus.NEED_USER_INPUT,
            summary="现有证据不足以输出强诊断结论，请补充现场状态后继续。",
            clarification_questions=[
                "请确认现场是否存在异响、异味、可见损坏或通信设备离线。",
                "请补充最近一次人工巡检结果或已执行的处置动作。",
            ],
            evidence_package_id=package.package_id if package else None,
            generated_at=utc_now(),
        )
        state["result"] = result
        return state

    async def _reason_generator(self, state: AgentWorkflowState) -> AgentWorkflowState:
        request = state["request_context"]
        package = state.get("evidence_package")
        evidence_ids = [item.evidence_id for item in package.ranked_evidence[:3]] if package else []
        cause = _infer_cause(request, package)
        confidence = 0.74 if evidence_ids else 0.35
        if state.get("clarification_answer"):
            confidence = min(confidence + 0.08, 0.9)
        state["result"] = DiagnosisResult(
            session_id=request.session_id,
            status=DiagnosisStatus.DRAFT_READY,
            summary=f"初步判断：{cause}。",
            candidate_causes=[
                CandidateCause(
                    cause=cause,
                    confidence=confidence,
                    supporting_evidence=evidence_ids,
                    missing_information=[] if confidence >= 0.5 else ["现场巡检信息"],
                    need_manual_confirmation=confidence < 0.6,
                )
            ],
            evidence_package_id=package.package_id if package else None,
            generated_at=utc_now(),
        )
        state["status"] = DiagnosisStatus.DRAFT_READY
        _append_event(state, "draft_ready", "已生成候选根因草稿", 82, {"cause": cause})
        return state

    async def _response_generator(self, state: AgentWorkflowState) -> AgentWorkflowState:
        request = state["request_context"]
        result = state.get("result")
        if result is None:
            state["status"] = DiagnosisStatus.FAILED
            state["failure_reason"] = "DIAGNOSIS_RESULT_MISSING"
            return state
        alarm_name = request.alarm.alarm_name if request.alarm else "当前告警"
        result.investigation_steps.extend(
            [
                f"复核 {alarm_name} 的触发时间、等级和持续时长。",
                "查看最近 15 分钟关键遥测趋势，确认异常是否持续扩大。",
                "按证据引用检查对应手册章节和历史工单处置动作。",
            ]
        )
        result.safety_notes.extend(
            [
                "涉及停机、断电或切换回路的处置必须由人工确认。",
                "远程数据缺失时不得输出强制执行类结论。",
            ]
        )
        result.ticket_suggestion = TicketSuggestion(
            action="create",
            summary=f"{alarm_name} 诊断建议工单草稿",
        )
        state["result"] = result
        _append_event(state, "response_generated", "已生成诊断答复和排查建议", 90, {})
        return state

    async def _rule_checker(self, state: AgentWorkflowState) -> AgentWorkflowState:
        state["status"] = DiagnosisStatus.REVIEWING
        result = state.get("result")
        package = state.get("evidence_package")
        if result is None:
            state["status"] = DiagnosisStatus.FAILED
            state["failure_reason"] = "RULE_CHECK_RESULT_MISSING"
            return state

        known_ids = {item.evidence_id for item in package.ranked_evidence} if package else set()
        for cause in result.candidate_causes:
            missing = [item for item in cause.supporting_evidence if item not in known_ids]
            if missing:
                state["status"] = DiagnosisStatus.FAILED
                state["failure_reason"] = "INVALID_EVIDENCE_REFERENCE"
                result.status = DiagnosisStatus.FAILED
                state["result"] = result
                _append_event(
                    state,
                    "rule_check_failed",
                    "诊断结果引用了不存在的证据",
                    95,
                    {"missing_evidence": missing},
                )
                return state

        state["status"] = DiagnosisStatus.COMPLETED
        result.status = DiagnosisStatus.COMPLETED
        state["result"] = result
        _append_event(state, "diagnosis_completed", "诊断完成", 100, {})
        return state

    async def _safe_tool_call(
        self,
        state: AgentWorkflowState,
        tool_name: str,
        tool: ToolFunction,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        try:
            result = await tool(self._registry, context, payload)
        except Exception as exc:
            state["tool_calls"].append(
                ToolCallSummary(
                    tool_name=tool_name,
                    status=ToolStatus.FAILED,
                    success=False,
                    error_code="TOOL_EXCEPTION",
                    error_message=type(exc).__name__,
                    trace_id=context.trace_id,
                    source_system="agent-workflow",
                )
            )
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.FAILED,
                data={},
                meta=ToolMeta(trace_id=context.trace_id, source_system="agent-workflow"),
                error_code="TOOL_EXCEPTION",
                error_message=type(exc).__name__,
            )
        state["tool_calls"].append(_tool_summary(tool_name, result))
        return result

    @staticmethod
    def _route_after_gap_detection(state: AgentWorkflowState) -> str:
        if state["status"] is DiagnosisStatus.FAILED:
            return "failed"
        if state["status"] is DiagnosisStatus.NEED_USER_INPUT:
            return "clarify"
        return "reason"


def _append_event(
    state: AgentWorkflowState,
    event: str,
    message: str,
    progress: int,
    data: dict[str, Any],
) -> None:
    request = state["request_context"]
    state["events"].append(
        DiagnosisStateEvent(
            event=event,
            session_id=request.session_id,
            trace_id=request.trace_id,
            timestamp=utc_now(),
            status=state["status"],
            message=message,
            progress=progress,
            data=data,
            payload={"message": message, "progress": progress, "data": data},
        )
    )


def _tool_context(request: RequestContext) -> ToolContext:
    return ToolContext(
        trace_id=request.trace_id,
        source_system=request.request_source,
        site_id=request.site_id,
        operator_id=request.user_id,
    )


def _tool_summary(tool_name: str, result: ProviderResult) -> ToolCallSummary:
    return ToolCallSummary(
        tool_name=tool_name,
        status=result.status,
        success=result.success,
        error_code=result.error_code,
        error_message=result.error_message,
        trace_id=result.meta.trace_id,
        source_system=result.meta.source_system,
        partial_result=result.meta.partial_result,
    )


def _infer_cause(request: RequestContext, package: EvidencePackage | None) -> str:
    text = " ".join(
        [
            request.message or "",
            request.alarm.alarm_name if request.alarm and request.alarm.alarm_name else "",
            " ".join(item.quote_text for item in package.ranked_evidence[:3]) if package else "",
        ]
    )
    if any(term in text for term in ("温度", "散热", "风扇", "冷却")):
        return "散热链路异常或风扇效率下降"
    if any(term in text for term in ("通讯", "通信", "交换机", "采集器")):
        return "通讯链路中断或采集设备异常"
    if any(term in text for term in ("电流", "采样", "传感器")):
        return "电流采样回路或传感器异常"
    if any(term in text for term in ("功率", "逆变")):
        return "功率输出受限或逆变器运行状态异常"
    return "设备运行状态异常，需结合现场信息确认根因"


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
