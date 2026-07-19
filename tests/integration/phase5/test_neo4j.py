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
        case_alarm_name = f"PCS{template.alarm_patterns[0]}"
        await provider.project_case(
            case_id="CASE-PHASE5-GRAPH",
            case_version=1,
            device_type=template.device_type,
            alarm_name=case_alarm_name,
            fault_cause=template.graph_relations[0].fault_cause,
            resolution_action="CASE-PHASE5-ACTION",
        )
        await provider.project_case(
            case_id="CASE-PHASE5-GRAPH",
            case_version=1,
            device_type=template.device_type,
            alarm_name=case_alarm_name,
            fault_cause=template.graph_relations[0].fault_cause,
            resolution_action="CASE-PHASE5-ACTION",
        )
        async with provider.driver.session(database=provider.database) as session:
            result = await session.run(
                """
                MATCH ()-[r]->()
                WHERE r.source_type = 'case' AND r.source_id = $case_id
                RETURN count(r) AS relation_count,
                       collect(DISTINCT type(r)) AS relation_types
                """,
                case_id="CASE-PHASE5-GRAPH",
            )
            record = await result.single()
        assert record is not None
        assert record["relation_count"] == 4
        assert set(record["relation_types"]) == {
            "CONFIRMS",
            "HAS_ALARM",
            "MAY_BE_CAUSED_BY",
            "MITIGATED_BY",
        }
        relations = await service.query(
            alarm_name=case_alarm_name,
            device_type=template.device_type,
            component=None,
            relation_depth=2,
            top_k=1,
        )
        assert len(relations) == 1
        assert "CASE-PHASE5-GRAPH" in relations[0].support_case_ids
        support_count = relations[0].support_count
        await provider.tombstone_case("CASE-PHASE5-GRAPH")
        async with provider.driver.session(database=provider.database) as session:
            result = await session.run(
                """
                MATCH ()-[r]->()
                WHERE r.source_type = 'case' AND r.source_id = $case_id
                RETURN count(r) AS relation_count
                """,
                case_id="CASE-PHASE5-GRAPH",
            )
            record = await result.single()
        assert record is not None
        assert record["relation_count"] == 0
        after = await service.query(
            alarm_name=case_alarm_name,
            device_type=template.device_type,
            component=None,
            relation_depth=2,
            top_k=1,
        )
        assert "CASE-PHASE5-GRAPH" not in after[0].support_case_ids
        assert after[0].support_count == support_count - 1
    finally:
        await provider.close()
