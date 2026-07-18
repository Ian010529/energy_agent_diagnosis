from energy_agent.agent.graph import FOUNDATION_NODE, compile_graph
from energy_agent.agent.nodes.base import traced_node
from energy_agent.agent.state import DiagnosisState
from energy_agent.contracts.common import SessionSource
from energy_agent.core.ids import new_id
from energy_agent.observability.tracing import LocalTracer


async def test_foundation_graph_compiles_and_runs() -> None:
    tracer = LocalTracer()

    async def foundation(state: DiagnosisState) -> dict[str, object]:
        return {"warnings": ["foundation-ok"]}

    graph = compile_graph(
        {FOUNDATION_NODE: traced_node(FOUNDATION_NODE, tracer, foundation)},
        [("START", FOUNDATION_NODE), (FOUNDATION_NODE, "END")],
    )
    result = await graph.ainvoke(
        DiagnosisState(
            session_id=new_id(),
            run_id=new_id(),
            trace_id=new_id(),
            source=SessionSource.CHAT,
        )
    )
    assert result["warnings"] == ["foundation-ok"]
