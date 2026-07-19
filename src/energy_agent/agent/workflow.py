from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from energy_agent.agent.nodes.base import NodeLogCallable, traced_node
from energy_agent.agent.state import (
    AlarmContext,
    ClarificationQuestion,
    DeviceContext,
    DiagnosisState,
    Evidence,
    PlanStep,
    ToolResultSummary,
)
from energy_agent.agent.templates.registry import (
    TemplateAmbiguousError,
    TemplateNotFoundError,
)
from energy_agent.agent.templates.routing import DEFAULT_TEMPLATE_REGISTRY
from energy_agent.agent.templates.rules import evaluate_candidate_rules
from energy_agent.contracts.common import DiagnosisIntent, DiagnosisPhase, RiskLevel
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


def _context(state: DiagnosisState) -> dict[str, object]:
    site_id = state.device_context.site_id if state.device_context else None
    return {
        "trace_id": state.trace_id,
        "source_system": "energy-agent",
        "site_id": site_id,
        "session_id": state.session_id,
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

    async def clarification_applier(state: DiagnosisState) -> dict[str, object]:
        return {
            "phase": DiagnosisPhase.EVIDENCE_READY,
            "clarification_questions": [],
            "errors": [],
        }

    async def plan_builder(state: DiagnosisState) -> dict[str, object]:
        assert state.alarm_context
        try:
            with tracer.start_span(
                "template.route",
                trace_id=state.trace_id,
                metadata={
                    "device_type": (
                        state.device_context.device_type if state.device_context else None
                    ),
                    "alarm_name": state.alarm_context.alarm_name,
                },
            ) as span:
                template, route_basis = DEFAULT_TEMPLATE_REGISTRY.route(
                    device_type=(
                        state.device_context.device_type if state.device_context else None
                    ),
                    alarm_name=state.alarm_context.alarm_name,
                    user_text=state.user_message,
                )
                span.set_output(
                    {
                        "template_id": template.template_id,
                        "template_version": template.template_version,
                        "route_basis": route_basis,
                    }
                )
        except (TemplateNotFoundError, TemplateAmbiguousError) as exc:
            return {
                "phase": DiagnosisPhase.NEED_USER_INPUT,
                "clarification_questions": [
                    ClarificationQuestion(
                        question_id="template_route",
                        question="请补充标准设备类型和准确告警名称。",
                        reason=str(exc),
                    )
                ],
                "errors": [str(exc)],
            }
        return {
            "diagnosis_template_id": template.template_id,
            "diagnosis_template_version": template.template_version,
            "alarm_category": template.alarm_category,
            "template_route_basis": route_basis,
            "phase": DiagnosisPhase.PLAN_READY,
            "plan": [
                PlanStep(step_id="S1", goal="查询设备画像", tool="get_device_profile"),
                PlanStep(step_id="S2", goal="查询告警详情", tool="get_alarm_detail"),
                PlanStep(step_id="S3", goal="查询最近时序窗口", tool="query_timeseries_window"),
                PlanStep(step_id="S4", goal="检索设备手册", tool="search_manual_chunks"),
                PlanStep(step_id="S5", goal="检索已审核相似工单", tool="search_similar_tickets"),
                PlanStep(step_id="S6", goal="查询图谱补充关系", tool="query_graph_relations"),
                *[
                    PlanStep(step_id=f"T{index}", goal=goal)
                    for index, goal in enumerate(template.plan_steps, 1)
                ],
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
        assert state.diagnosis_template_id
        template = DEFAULT_TEMPLATE_REGISTRY.get(state.diagnosis_template_id)
        end = (
            state.alarm_context.trigger_time
            if state.alarm_context and state.alarm_context.trigger_time
            else utc_now()
        )
        start = end - timedelta(minutes=template.default_window_minutes)
        result = await executor.execute(
            "query_timeseries_window",
            {
                "context": _context(state),
                "device_id": state.device_context.device_id,
                "measurements": template.measurements,
                "metrics": template.metrics,
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

    async def graph_fetcher(state: DiagnosisState) -> dict[str, object]:
        assert state.device_context and state.alarm_context
        result = await executor.execute(
            "query_graph_relations",
            {
                "context": _context(state),
                "alarm_name": state.alarm_context.alarm_name,
                "device_type": state.device_context.device_type,
                "relation_depth": 2,
                "top_k": 2,
            },
            state.trace_id,
        )
        tool_data["query_graph_relations"] = result
        degraded = list(state.degraded_components)
        if result.status == ToolStatus.DEGRADED:
            degraded.append("neo4j")
        return {
            "tool_results": [
                *state.tool_results,
                _tool_summary("query_graph_relations", result),
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
                    metadata={
                        "device_type": data["device_type"],
                        "device_model": data["device_model"],
                        "manufacturer": data["manufacturer"],
                    },
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
        for name in (
            "search_manual_chunks",
            "search_similar_tickets",
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
                source_type = str(
                    row.get("source_type", "manual" if name == "search_manual_chunks" else "ticket")
                )
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
        graph = tool_data.get("query_graph_relations")
        if graph and graph.success and isinstance(graph.data, dict):
            assert state.alarm_context
            relations = graph.data.get("relations", [])
            if isinstance(relations, list):
                for row in relations[:2]:
                    if not isinstance(row, dict):
                        continue
                    support_count = int(row.get("support_count", 0))
                    reliability = min(0.60 + min(support_count, 2) * 0.05, 0.70)
                    alarm_name = str(row.get("alarm_name", state.alarm_context.alarm_name))
                    fault_cause = str(row["fault_cause"])
                    evidence.append(
                        Evidence(
                            evidence_id=f"graph:{alarm_name}:{fault_cause}",
                            source_type="graph",
                            source_id=f"{alarm_name}->{fault_cause}",
                            summary=(
                                f"{alarm_name} 可能关联 {fault_cause}；"
                                f"部件 {row.get('component') or '未知'}；"
                                f"审核案例支撑 {support_count}"
                            ),
                            citation=f"[图谱: {alarm_name} -> {fault_cause}]",
                            verified=False,
                            reliability=reliability,
                            relevance=0.65,
                            source_reliability=reliability,
                            need_manual_confirmation=True,
                            metadata=row,
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
        if not types.intersection({"manual", "ticket", "case"}):
            gaps.append("手册和已审核工单证据缺失")
        return {"errors": gaps}

    async def clarification_generator(state: DiagnosisState) -> dict[str, object]:
        template = (
            DEFAULT_TEMPLATE_REGISTRY.get(state.diagnosis_template_id)
            if state.diagnosis_template_id
            else None
        )
        questions = []
        for index, gap in enumerate(state.errors[:3], 1):
            text = (
                template.clarification_rules[min(index - 1, len(template.clarification_rules) - 1)]
                if "时序" in gap and template
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
        assert state.diagnosis_template_id
        template = DEFAULT_TEMPLATE_REGISTRY.get(state.diagnosis_template_id)
        feedback = " ".join(item.answer for item in state.user_feedback)
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
            with tracer.start_span(
                "template.rule_evaluate",
                trace_id=state.trace_id,
                metadata={
                    "template_id": template.template_id,
                    "template_version": template.template_version,
                },
            ):
                causes = evaluate_candidate_rules(template, state.evidence, feedback)
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
        assert state.diagnosis_template_id
        template = DEFAULT_TEMPLATE_REGISTRY.get(state.diagnosis_template_id)
        result = {
            "summary": (
                "已基于设备、告警、时序与知识证据形成候选诊断，需按顺序现场确认。"
                if state.candidate_causes
                else "当前证据不足以形成候选根因，建议人工接管。"
            ),
            "candidate_causes": [item.model_dump(mode="json") for item in state.candidate_causes],
            "evidence": [item.model_dump(mode="json") for item in state.evidence],
            "inspection_steps": template.inspection_steps,
            "safety_notes": template.safety_notes,
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
        non_graph_types = {
            item.source_type
            for item in state.evidence
            if item.source_type not in {"graph", "device", "alarm"}
        }
        graph_only = any(
            cause.supporting_evidence
            and all(ref.startswith("graph:") for ref in cause.supporting_evidence)
            for cause in state.candidate_causes
        )
        if graph_only and not non_graph_types:
            return {"errors": [*state.errors, "图谱证据需人工确认"]}
        return {"phase": DiagnosisPhase.REVIEWING}

    async def memory_writer_node(state: DiagnosisState) -> dict[str, object]:
        await memory_writer(state)
        return {"phase": DiagnosisPhase.COMPLETED}

    nodes = {
        "intent_router": intent_router,
        "entity_parser": entity_parser,
        "clarification_applier": clarification_applier,
        "plan_builder": plan_builder,
        "tool_dispatcher": tool_dispatcher,
        "timeseries_fetcher": timeseries_fetcher,
        "ticket_fetcher": ticket_fetcher,
        "doc_retriever": doc_retriever,
        "graph_fetcher": graph_fetcher,
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
    graph.add_conditional_edges(
        "intent_router",
        lambda state: (
            "followup"
            if state.followup_mode == "answer_clarification" and bool(state.evidence)
            else "initial"
        ),
        {"followup": "clarification_applier", "initial": "entity_parser"},
    )
    graph.add_edge("clarification_applier", "gap_detector")
    graph.add_conditional_edges(
        "entity_parser",
        lambda state: "clarify" if state.phase == DiagnosisPhase.NEED_USER_INPUT else "dispatch",
        {"clarify": "clarification_generator", "dispatch": "tool_dispatcher"},
    )
    graph.add_edge("tool_dispatcher", "plan_builder")
    graph.add_conditional_edges(
        "plan_builder",
        lambda state: "clarify" if state.phase == DiagnosisPhase.NEED_USER_INPUT else "fetch",
        {"clarify": "clarification_generator", "fetch": "timeseries_fetcher"},
    )
    graph.add_edge("timeseries_fetcher", "ticket_fetcher")
    graph.add_edge("ticket_fetcher", "doc_retriever")
    graph.add_edge("doc_retriever", "graph_fetcher")
    graph.add_edge("graph_fetcher", "evidence_aggregator")
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
