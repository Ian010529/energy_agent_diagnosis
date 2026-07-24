from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from energy_agent.agent.events import DiagnosisEventEmitter, NoopDiagnosisEventEmitter
from energy_agent.agent.nodes.base import NodeLogCallable, traced_node
from energy_agent.agent.nodes.diagnosis import (
    DiagnosisNodeDependencies,
    _extract_entity_ids,
    build_diagnosis_nodes,
)
from energy_agent.agent.ports import MemoryWriterPort, ModelGenerationPort, ToolExecutorPort
from energy_agent.agent.state import DiagnosisState
from energy_agent.contracts.common import DiagnosisPhase
from energy_agent.guardrails.service import GuardrailService
from energy_agent.observability.tracing import Tracer
from energy_agent.templates.routing import DEFAULT_TEMPLATE_REGISTRY

__all__ = ["_extract_entity_ids", "build_diagnosis_graph"]


def build_diagnosis_graph(
    executor: ToolExecutorPort,
    tracer: Tracer,
    *,
    memory_writer: MemoryWriterPort,
    step_logger: NodeLogCallable | None = None,
    model_gateway: ModelGenerationPort | None = None,
    event_emitter: DiagnosisEventEmitter | None = None,
) -> Any:
    emitter = event_emitter or NoopDiagnosisEventEmitter()
    nodes = build_diagnosis_nodes(
        DiagnosisNodeDependencies(
            executor=executor,
            tracer=tracer,
            templates=DEFAULT_TEMPLATE_REGISTRY,
            guardrails=GuardrailService(),
            model=model_gateway,
            emitter=emitter,
        ),
        memory_writer=memory_writer,
    )
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
        lambda state: (
            "clarify"
            if state.phase == DiagnosisPhase.NEED_USER_INPUT or bool(state.errors)
            else "fetch"
        ),
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
