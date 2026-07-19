from energy_agent.agent.templates.contracts import DiagnosisTemplate
from energy_agent.graph.contracts import GraphRelation
from energy_agent.providers.neo4j import Neo4jProvider


class GraphService:
    def __init__(self, provider: Neo4jProvider | None) -> None:
        self.provider = provider

    async def bootstrap_template(self, template: DiagnosisTemplate) -> None:
        if not self.provider:
            raise RuntimeError("GRAPH_DISABLED")
        await self.provider.project_template(
            {
                "template_id": template.template_id,
                "template_version": template.template_version,
                "device_type": template.device_type,
                "alarm_id": template.template_id,
                "alarm_name": template.alarm_patterns[0],
                "relations": [item.model_dump(mode="json") for item in template.graph_relations],
            }
        )

    async def query(
        self,
        *,
        alarm_name: str,
        device_type: str | None,
        component: str | None,
        relation_depth: int,
        top_k: int,
    ) -> list[GraphRelation]:
        if not self.provider:
            raise RuntimeError("GRAPH_DISABLED")
        return await self.provider.query_relations(
            alarm_name=alarm_name,
            device_type=device_type,
            component=component,
            relation_depth=relation_depth,
            top_k=top_k,
        )
