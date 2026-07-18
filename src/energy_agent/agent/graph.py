from collections.abc import Mapping, Sequence
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from energy_agent.agent.nodes.base import NodeCallable
from energy_agent.agent.state import DiagnosisState

FOUNDATION_NODE = "foundation_node"


def compile_graph(
    nodes: Mapping[str, NodeCallable],
    edges: Sequence[tuple[str, str]],
) -> Any:
    """Compile caller-supplied nodes without installing placeholder diagnosis behavior."""
    graph = StateGraph(DiagnosisState)
    for name, node in nodes.items():
        graph.add_node(name, cast(Any, node))
    for source, target in edges:
        graph.add_edge(START if source == "START" else source, END if target == "END" else target)
    return graph.compile()
