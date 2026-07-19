import pytest

from energy_agent.agent.templates.definitions import TEMPLATES
from energy_agent.graph.service import GraphService
from energy_agent.providers.neo4j import Neo4jProvider

pytestmark = pytest.mark.integration


def _provider() -> Neo4jProvider:
    return Neo4jProvider(
        uri="neo4j://localhost:7687",
        user="neo4j",
        password="energy_neo4j_dev",
        database="neo4j",
        timeout_seconds=5,
    )


@pytest.mark.asyncio
async def test_neo4j_constraints_template_bootstrap_case_projection_and_tombstone() -> None:
    provider = _provider()
    service = GraphService(provider)
    try:
        await provider.verify()
        await provider.ensure_schema()
        template = TEMPLATES[1]
        await service.bootstrap_template(template)
        await service.bootstrap_template(template)
        await provider.project_case(
            case_id="CASE-PHASE5-GRAPH",
            case_version=1,
            fault_cause=template.graph_relations[0].fault_cause,
        )
        relations = await service.query(
            alarm_name=template.alarm_patterns[0],
            device_type=template.device_type,
            component=None,
            relation_depth=2,
            top_k=1,
        )
        assert len(relations) == 1
        assert relations[0].support_case_ids == ["CASE-PHASE5-GRAPH"]
        await provider.tombstone_case("CASE-PHASE5-GRAPH")
        after = await service.query(
            alarm_name=template.alarm_patterns[0],
            device_type=template.device_type,
            component=None,
            relation_depth=2,
            top_k=1,
        )
        assert after[0].support_count == 0
    finally:
        await provider.close()
