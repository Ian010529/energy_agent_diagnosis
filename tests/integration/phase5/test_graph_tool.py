import pytest

from energy_agent.agent.templates.definitions import TEMPLATES
from energy_agent.graph.service import GraphService
from energy_agent.observability.tracing import LocalTracer
from energy_agent.providers.neo4j import Neo4jProvider
from energy_agent.tools.contracts import GraphRelationsInput, ToolContext, ToolStatus
from energy_agent.tools.executor import ToolExecutor
from energy_agent.tools.implementations.graph_tools import register_graph_tool
from energy_agent.tools.registry import ToolRegistry

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_graph_tool_queries_real_neo4j_through_registry_and_degrades() -> None:
    provider = Neo4jProvider(
        uri="neo4j://localhost:7687",
        user="neo4j",
        password="energy_neo4j_dev",
        database="neo4j",
        timeout_seconds=5,
    )
    template = TEMPLATES[3]
    service = GraphService(provider)
    try:
        await provider.ensure_schema()
        await service.bootstrap_template(template)
        registry = ToolRegistry()
        register_graph_tool(registry, service)
        payload = GraphRelationsInput(
            context=ToolContext(trace_id="trace", source_system="integration"),
            alarm_name=template.alarm_patterns[0],
            device_type=template.device_type,
            top_k=2,
        ).model_dump()
        result = await ToolExecutor(registry, LocalTracer()).execute(
            "query_graph_relations", payload, "trace"
        )
        assert result.status == ToolStatus.OK
        assert result.data["relations"]
    finally:
        await provider.close()

    disabled = ToolRegistry()
    register_graph_tool(disabled, GraphService(None))
    result = await ToolExecutor(disabled, LocalTracer()).execute(
        "query_graph_relations", payload, "trace"
    )
    assert result.status == ToolStatus.DEGRADED
    assert result.error_code == "GRAPH_DISABLED"
