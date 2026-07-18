from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from energy_agent.agent.nodes.base import NodeLogCallable, traced_node
from energy_agent.agent.state import (
    AlarmContext,
    CandidateCause,
    ClarificationQuestion,
    DeviceContext,
    DiagnosisState,
    Evidence,
    PlanStep,
    ToolResultSummary,
)
from energy_agent.contracts.common import DiagnosisIntent, DiagnosisPhase, RiskLevel
from energy_agent.core.errors import UnsupportedIntentError
from energy_agent.core.time import utc_now
from energy_agent.model.gateway import (
    CandidateCauseEnvelope,
    ClarificationEnvelope,
    ModelGateway,
)
from energy_agent.observability.tracing import Tracer
from energy_agent.tools.contracts import ToolResult, ToolStatus
from energy_agent.tools.executor import ToolExecutor

MEMORY_WRITER = Callable[[DiagnosisState], Awaitable[None]]
PCS_TEMPLATE_ID = "pcs_temperature_abnormal_v1"
METRICS = [
    "cabinet_temperature",
    "ambient_temperature",
    "fan_speed",
    "fan_status",
    "output_power",
    "dc_current",
]


def _context(state: DiagnosisState) -> dict[str, object]:
    site_id = state.device_context.site_id if state.device_context else None
    return {
        "trace_id": state.trace_id,
        "source_system": "energy-agent",
        "site_id": site_id,
    }


def _tool_summary(name: str, result: ToolResult) -> ToolResultSummary:
    return ToolResultSummary(
        tool_name=name,
        status=result.status,
        summary=f"{name}:{result.status}",
    )


def build_diagnosis_graph(
    executor: ToolExecutor,
    tracer: Tracer,
    *,
    memory_writer: MEMORY_WRITER,
    step_logger: NodeLogCallable | None = None,
    model_gateway: ModelGateway | None = None,
) -> Any:
    tool_data: dict[str, Any] = {}

    async def intent_router(state: DiagnosisState) -> dict[str, object]:
        intent = (
            DiagnosisIntent.FOLLOWUP_CLARIFICATION
            if state.user_feedback
            else DiagnosisIntent.FAULT_DIAGNOSIS
        )
        alarm_name = state.alarm_context.alarm_name if state.alarm_context else ""
        text = f"{alarm_name} {state.user_message or ''}"
        if state.source.value != "alarm" and not any(
            term in text for term in ("温度", "散热", "PCS", "机柜")
        ):
            raise UnsupportedIntentError("Phase 2 only supports PCS cabinet temperature diagnosis")
        return {"intent": intent}

    async def entity_parser(state: DiagnosisState) -> dict[str, object]:
        if not state.device_context or not state.alarm_context:
            questions = [
                ClarificationQuestion(
                    question_id="missing_entity",
                    question="请补充设备编号和告警编号。",
                    reason="诊断需要可追溯的设备与告警实体",
                )
            ]
            return {
                "phase": DiagnosisPhase.NEED_USER_INPUT,
                "clarification_questions": questions,
                "errors": ["设备或告警实体缺失"],
            }
        return {}

    async def plan_builder(state: DiagnosisState) -> dict[str, object]:
        return {
            "diagnosis_template_id": PCS_TEMPLATE_ID,
            "phase": DiagnosisPhase.PLAN_READY,
            "plan": [
                PlanStep(step_id="S1", goal="查询设备画像", tool="get_device_profile"),
                PlanStep(step_id="S2", goal="查询告警详情", tool="get_alarm_detail"),
                PlanStep(step_id="S3", goal="查询最近时序窗口", tool="query_timeseries_window"),
                PlanStep(step_id="S4", goal="检索设备手册", tool="search_manual_chunks"),
                PlanStep(step_id="S5", goal="检索已审核相似工单", tool="search_similar_tickets"),
                PlanStep(step_id="S6", goal="归并证据并检测缺口"),
                PlanStep(step_id="S7", goal="生成候选根因或补充问题"),
                PlanStep(step_id="S8", goal="生成答复并进行规则校验"),
                PlanStep(step_id="S9", goal="写入会话记忆和诊断结果"),
            ],
        }

    async def tool_dispatcher(state: DiagnosisState) -> dict[str, object]:
        assert state.device_context and state.alarm_context
        device = await executor.execute(
            "get_device_profile",
            {"context": _context(state), "device_id": state.device_context.device_id},
            state.trace_id,
        )
        alarm = await executor.execute(
            "get_alarm_detail",
            {
                "context": _context(state),
                "alarm_id": state.alarm_context.alarm_id,
                "device_id": state.device_context.device_id,
            },
            state.trace_id,
        )
        tool_data["get_device_profile"] = device
        tool_data["get_alarm_detail"] = alarm
        updates: dict[str, object] = {
            "phase": DiagnosisPhase.DATA_FETCHING,
            "tool_results": [
                *state.tool_results,
                _tool_summary("get_device_profile", device),
                _tool_summary("get_alarm_detail", alarm),
            ],
        }
        if device.success:
            data = device.data
            updates["device_context"] = DeviceContext(
                site_id=str(data["site_id"]),
                device_id=str(data["device_id"]),
                device_type=str(data["device_type"]),
                device_model=str(data["device_model"]),
                manufacturer=str(data["manufacturer"]),
            )
        if alarm.success:
            data = alarm.data
            updates["alarm_context"] = AlarmContext(
                alarm_id=str(data["alarm_id"]),
                alarm_name=str(data["alarm_name"]),
                trigger_time=data["trigger_time"],
            )
        return updates

    async def timeseries_fetcher(state: DiagnosisState) -> dict[str, object]:
        assert state.device_context
        end = (
            state.alarm_context.trigger_time
            if state.alarm_context and state.alarm_context.trigger_time
            else utc_now()
        )
        start = end - timedelta(minutes=30)
        result = await executor.execute(
            "query_timeseries_window",
            {
                "context": _context(state),
                "device_id": state.device_context.device_id,
                "metrics": METRICS,
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            },
            state.trace_id,
        )
        tool_data["query_timeseries_window"] = result
        degraded = state.degraded_components
        if result.status in {ToolStatus.TIMEOUT, ToolStatus.DEGRADED, ToolStatus.FAILED}:
            degraded = [*degraded, "influxdb"]
        return {
            "tool_results": [
                *state.tool_results,
                _tool_summary("query_timeseries_window", result),
            ],
            "degraded_components": degraded,
        }

    async def ticket_fetcher(state: DiagnosisState) -> dict[str, object]:
        assert state.device_context and state.alarm_context
        retrieval_query = state.user_message or state.alarm_context.alarm_name
        result = await executor.execute(
            "search_similar_tickets",
            {
                "context": _context(state),
                "query": retrieval_query,
                "filters": {
                    "device_type": state.device_context.device_type,
                    "device_model": state.device_context.device_model,
                    "manufacturer": state.device_context.manufacturer,
                    "alarm_name": state.alarm_context.alarm_name,
                },
                "verified_only": True,
            },
            state.trace_id,
        )
        tool_data["search_similar_tickets"] = result
        degraded = list(state.degraded_components)
        if isinstance(result.data, dict):
            metadata = result.data.get("retrieval_metadata", {})
            if isinstance(metadata, dict):
                degraded.extend(str(item) for item in metadata.get("degraded_components", []))
        return {
            "tool_results": [
                *state.tool_results,
                _tool_summary("search_similar_tickets", result),
            ],
            "degraded_components": sorted(set(degraded)),
        }

    async def doc_retriever(state: DiagnosisState) -> dict[str, object]:
        assert state.device_context and state.alarm_context
        retrieval_query = state.user_message or state.alarm_context.alarm_name
        result = await executor.execute(
            "search_manual_chunks",
            {
                "context": _context(state),
                "query": retrieval_query,
                "filters": {
                    "device_type": state.device_context.device_type,
                    "device_model": state.device_context.device_model,
                    "manufacturer": state.device_context.manufacturer,
                    "alarm_name": state.alarm_context.alarm_name,
                },
            },
            state.trace_id,
        )
        tool_data["search_manual_chunks"] = result
        degraded = list(state.degraded_components)
        if isinstance(result.data, dict):
            metadata = result.data.get("retrieval_metadata", {})
            if isinstance(metadata, dict):
                degraded.extend(str(item) for item in metadata.get("degraded_components", []))
        return {
            "tool_results": [
                *state.tool_results,
                _tool_summary("search_manual_chunks", result),
            ],
            "degraded_components": sorted(set(degraded)),
        }

    async def evidence_aggregator(state: DiagnosisState) -> dict[str, object]:
        evidence: list[Evidence] = []
        device = tool_data.get("get_device_profile")
        alarm = tool_data.get("get_alarm_detail")
        ts = tool_data.get("query_timeseries_window")
        if device and device.success:
            data = device.data
            evidence.append(
                Evidence(
                    evidence_id=f"device:{data['device_id']}",
                    source_type="device",
                    source_id=str(data["device_id"]),
                    summary=f"{data['device_type']} {data['device_model']}，状态 {data['status']}",
                    citation=f"[设备: {data['device_id']}]",
                    verified=True,
                    reliability=1,
                    relevance=1,
                )
            )
        if alarm and alarm.success:
            data = alarm.data
            evidence.append(
                Evidence(
                    evidence_id=f"alarm:{data['alarm_id']}",
                    source_type="alarm",
                    source_id=str(data["alarm_id"]),
                    summary=f"{data['alarm_name']}，等级 {data['alarm_level']}",
                    citation=f"[告警: {data['alarm_id']}]",
                    verified=True,
                    reliability=1,
                    relevance=1,
                )
            )
        if ts and ts.success and state.device_context:
            rising = [
                metric for metric, summary in ts.data.items() if summary.get("trend") == "rising"
            ]
            evidence.append(
                Evidence(
                    evidence_id=f"timeseries:{state.device_context.device_id}:{state.run_id}",
                    source_type="timeseries",
                    source_id=state.device_context.device_id,
                    summary=f"上升指标: {', '.join(rising) or '无'}；统计摘要已裁剪",
                    citation=(
                        f"[时序: device={state.device_context.device_id}, window={state.run_id}]"
                    ),
                    verified=True,
                    reliability=0.95,
                    relevance=0.95,
                    metadata={"metrics": ts.data},
                )
            )
        for name, source_type in (
            ("search_manual_chunks", "manual"),
            ("search_similar_tickets", "ticket"),
        ):
            result = tool_data.get(name)
            if not result or not result.success:
                continue
            if not isinstance(result.data, dict):
                continue
            package = result.data
            ranked = package.get("ranked_evidence", [])
            if not isinstance(ranked, list):
                continue
            for row in ranked:
                if not isinstance(row, dict):
                    continue
                source_id = str(row["source_id"])
                citation = str(row["citation"])
                summary = str(row["content_summary"])[:500]
                metadata = row.get("metadata", {})
                verified = bool(isinstance(metadata, dict) and metadata.get("verified"))
                reliability = float(row["source_reliability"])
                evidence.append(
                    Evidence(
                        evidence_id=(
                            f"{source_type}:{source_id}:{row.get('chunk_id')}"
                            if row.get("chunk_id")
                            else f"{source_type}:{source_id}"
                        ),
                        source_type=source_type,
                        source_id=source_id,
                        summary=summary,
                        citation=citation,
                        verified=verified,
                        reliability=reliability,
                        relevance=float(row["relevance_to_alarm"]),
                        retrieval_score=float(row["retrieval_score"]),
                        source_reliability=reliability,
                        verification_score=float(row["verification_score"]),
                        freshness_score=float(row["freshness_score"]),
                        relevance_to_alarm=float(row["relevance_to_alarm"]),
                        final_score=float(row["final_score"]),
                        chunk_id=(str(row["chunk_id"]) if row.get("chunk_id") else None),
                        package_id=(str(row["package_id"]) if row.get("package_id") else None),
                        metadata={
                            "retrieval_mode": result.meta.retrieval_mode,
                            **(metadata if isinstance(metadata, dict) else {}),
                        },
                    )
                )
        deduped = {item.evidence_id: item for item in evidence}
        values = list(deduped.values())
        return {
            "phase": DiagnosisPhase.EVIDENCE_READY,
            "evidence": values,
            "evidence_refs": [item.evidence_id for item in values],
        }

    async def gap_detector(state: DiagnosisState) -> dict[str, object]:
        types = {item.source_type for item in state.evidence}
        gaps = []
        if "device" not in types:
            gaps.append("设备画像缺失")
        if "alarm" not in types:
            gaps.append("告警详情缺失")
        if "timeseries" not in types and not state.user_feedback:
            gaps.append("关键时序不可用")
        if not types.intersection({"manual", "ticket"}):
            gaps.append("手册和已审核工单证据缺失")
        return {"errors": gaps}

    async def clarification_generator(state: DiagnosisState) -> dict[str, object]:
        questions = []
        for index, gap in enumerate(state.errors[:3], 1):
            text = (
                "请现场确认散热风扇是否运转、是否有异常噪音。"
                if "时序" in gap
                else "请补充对应设备或现场检查信息。"
            )
            questions.append(
                ClarificationQuestion(
                    question_id=f"gap_{index}",
                    question=text,
                    reason=gap,
                )
            )
        if model_gateway and questions:
            enhanced = await model_gateway.generate(
                trace_id=state.trace_id,
                session_id=state.session_id,
                node_name="clarification_generator",
                prompt_version="diag.clarification_generator.v1.0",
                system_prompt=("只根据缺口生成1到3个结构化补充问题，不推断设备事实。"),
                evidence_package={
                    "gaps": state.errors,
                    "template_questions": [item.model_dump(mode="json") for item in questions],
                },
                output_schema=ClarificationEnvelope,
            )
            if isinstance(enhanced, ClarificationEnvelope):
                questions = enhanced.clarification_questions[:3]
        return {
            "phase": DiagnosisPhase.NEED_USER_INPUT,
            "clarification_questions": questions,
        }

    async def reason_generator(state: DiagnosisState) -> dict[str, object]:
        causes: list[CandidateCause] = []
        by_type: dict[str, list[Evidence]] = {}
        for item in state.evidence:
            by_type.setdefault(item.source_type, []).append(item)
        all_text = " ".join(item.summary for item in state.evidence)
        feedback = " ".join(item.answer for item in state.user_feedback)

        def refs(*terms: str) -> list[str]:
            matched = [
                item.evidence_id
                for item in state.evidence
                if any(term in item.summary for term in terms)
            ]
            return matched or [item.evidence_id for item in state.evidence[:2]]

        with tracer.start_generation(
            "llm.reason_generator",
            trace_id=state.trace_id,
            model=None,
            metadata={
                "prompt_version": "diag.reason_generator.v1.0",
                "provider": "rules",
                "fallback": True,
            },
        ) as generation:
            if any(term in all_text + feedback for term in ("风扇", "不转", "转速")):
                causes.append(
                    CandidateCause(
                        cause="散热风扇失效或转速异常",
                        confidence=0.82 if "不转" in feedback else 0.72,
                        supporting_evidence=refs("风扇", "转速"),
                        missing_information=["现场确认风扇供电与机械状态"],
                        need_manual_confirmation=True,
                    )
                )
            if any(term in all_text + feedback for term in ("滤网", "堵塞", "风道")):
                causes.append(
                    CandidateCause(
                        cause="滤网或风道堵塞",
                        confidence=0.68,
                        supporting_evidence=refs("滤网", "堵塞", "风道"),
                        missing_information=["现场检查滤网压差与积尘"],
                        need_manual_confirmation=True,
                    )
                )
            ts_text = " ".join(item.summary for item in by_type.get("timeseries", []))
            if any(term in all_text + ts_text for term in ("环境温度", "负荷", "output_power")):
                causes.append(
                    CandidateCause(
                        cause="环境温度或负荷过高",
                        confidence=0.62,
                        supporting_evidence=refs("环境温度", "负荷", "功率"),
                        need_manual_confirmation=True,
                    )
                )
            if any(term in all_text for term in ("传感器", "漂移")):
                causes.append(
                    CandidateCause(
                        cause="温度传感器漂移",
                        confidence=0.55,
                        supporting_evidence=refs("传感器", "漂移"),
                        missing_information=["使用独立测温仪交叉校验"],
                        need_manual_confirmation=True,
                    )
                )
            generation.set_output({"candidate_count": len(causes), "provider": "rules"})
        if model_gateway and causes:
            enhanced = await model_gateway.generate(
                trace_id=state.trace_id,
                session_id=state.session_id,
                node_name="reason_generator",
                prompt_version="diag.reason_generator.v1.0",
                system_prompt=("仅依据裁剪证据生成2到4个候选根因；引用必须使用已有evidence_id。"),
                evidence_package={
                    "evidence": [item.model_dump(mode="json") for item in state.evidence],
                    "rule_candidates": [item.model_dump(mode="json") for item in causes],
                },
                output_schema=CandidateCauseEnvelope,
            )
            if isinstance(enhanced, CandidateCauseEnvelope):
                causes = enhanced.candidate_causes[:4]
        return {
            "phase": DiagnosisPhase.DRAFT_READY,
            "candidate_causes": causes[:4],
        }

    async def response_generator(state: DiagnosisState) -> dict[str, object]:
        result = {
            "summary": (
                "已基于设备、告警、时序与知识证据形成候选诊断，需按顺序现场确认。"
                if state.candidate_causes
                else "当前证据不足以形成候选根因，建议人工接管。"
            ),
            "candidate_causes": [item.model_dump(mode="json") for item in state.candidate_causes],
            "evidence": [item.model_dump(mode="json") for item in state.evidence],
            "inspection_steps": [
                "核对柜内温度与独立测温值",
                "检查风扇运行、供电和转速",
                "检查滤网积尘与风道通畅情况",
                "核对环境温度和当前负荷",
            ],
            "safety_notes": ["涉及停机、断电或回路切换时必须由授权人员人工确认并执行。"],
            "missing_information": sorted(
                {
                    missing
                    for cause in state.candidate_causes
                    for missing in cause.missing_information
                }
            ),
            "recommend_ticket": not state.candidate_causes or bool(state.degraded_components),
            "risk_level": RiskLevel.MEDIUM,
            "warnings": state.warnings,
            "degraded_components": sorted(set(state.degraded_components)),
        }
        with tracer.start_generation(
            "llm.response_generator",
            trace_id=state.trace_id,
            model=None,
            metadata={
                "prompt_version": "diag.response_generator.v1.0",
                "provider": "rules",
                "fallback": True,
            },
        ) as generation:
            generation.set_output({"structured": True, "provider": "rules"})
        if model_gateway:
            from energy_agent.contracts.diagnosis import StructuredDiagnosisResult

            enhanced = await model_gateway.generate(
                trace_id=state.trace_id,
                session_id=state.session_id,
                node_name="response_generator",
                prompt_version="diag.response_generator.v1.0",
                system_prompt=("只基于提供的结构化草稿润色，不新增事实、证据或高风险自动操作。"),
                evidence_package=cast(dict[str, object], result),
                output_schema=StructuredDiagnosisResult,
            )
            if isinstance(enhanced, StructuredDiagnosisResult):
                result = enhanced.model_dump(mode="json")
        return {"final_response": result}

    async def rule_checker(state: DiagnosisState) -> dict[str, object]:
        evidence_ids = {item.evidence_id for item in state.evidence}
        invalid = [
            ref
            for cause in state.candidate_causes
            for ref in cause.supporting_evidence
            if ref not in evidence_ids
        ]
        if invalid:
            return {"errors": [*state.errors, "候选根因包含未知证据引用"]}
        if not state.candidate_causes:
            return {"errors": [*state.errors, "无可验证候选根因"]}
        return {"phase": DiagnosisPhase.REVIEWING}

    async def memory_writer_node(state: DiagnosisState) -> dict[str, object]:
        await memory_writer(state)
        return {"phase": DiagnosisPhase.COMPLETED}

    nodes = {
        "intent_router": intent_router,
        "entity_parser": entity_parser,
        "plan_builder": plan_builder,
        "tool_dispatcher": tool_dispatcher,
        "timeseries_fetcher": timeseries_fetcher,
        "ticket_fetcher": ticket_fetcher,
        "doc_retriever": doc_retriever,
        "evidence_aggregator": evidence_aggregator,
        "gap_detector": gap_detector,
        "clarification_generator": clarification_generator,
        "reason_generator": reason_generator,
        "response_generator": response_generator,
        "rule_checker": rule_checker,
        "memory_writer": memory_writer_node,
    }
    graph = StateGraph(DiagnosisState)
    for name, node in nodes.items():
        graph.add_node(name, cast(Any, traced_node(name, tracer, node, step_logger)))
    graph.add_edge(START, "intent_router")
    graph.add_edge("intent_router", "entity_parser")
    graph.add_conditional_edges(
        "entity_parser",
        lambda state: "clarify" if state.phase == DiagnosisPhase.NEED_USER_INPUT else "plan",
        {"clarify": "clarification_generator", "plan": "plan_builder"},
    )
    graph.add_edge("plan_builder", "tool_dispatcher")
    graph.add_edge("tool_dispatcher", "timeseries_fetcher")
    graph.add_edge("timeseries_fetcher", "ticket_fetcher")
    graph.add_edge("ticket_fetcher", "doc_retriever")
    graph.add_edge("doc_retriever", "evidence_aggregator")
    graph.add_edge("evidence_aggregator", "gap_detector")
    graph.add_conditional_edges(
        "gap_detector",
        lambda state: "clarify" if state.errors else "reason",
        {"clarify": "clarification_generator", "reason": "reason_generator"},
    )
    graph.add_edge("clarification_generator", END)
    graph.add_edge("reason_generator", "response_generator")
    graph.add_edge("response_generator", "rule_checker")
    graph.add_conditional_edges(
        "rule_checker",
        lambda state: "clarify" if state.errors else "write",
        {"clarify": "clarification_generator", "write": "memory_writer"},
    )
    graph.add_edge("memory_writer", END)
    return graph.compile()
