from energy_agent.graph.contracts import GraphPort, GraphRelation
from energy_agent.templates.contracts import DiagnosisTemplate


class GraphService:
    def __init__(self, provider: GraphPort | None) -> None:
        self._provider = provider

    @property
    def available(self) -> bool:
        return self._provider is not None

    async def project_template(self, template: DiagnosisTemplate) -> None:
        if not self._provider:
            raise RuntimeError("GRAPH_DISABLED")
        await self._provider.project_template(
            {
                "template_id": template.template_id,
                "template_version": template.template_version,
                "device_type": template.device_type,
                "alarm_id": template.template_id,
                "alarm_name": template.alarm_patterns[0],
                "relations": [item.model_dump(mode="json") for item in template.graph_relations],
            }
        )

    async def bootstrap_template(self, template: DiagnosisTemplate) -> None:
        await self.project_template(template)

    async def project_case(
        self,
        *,
        case_id: str,
        case_version: int,
        device_type: str,
        alarm_name: str,
        fault_cause: str,
        resolution_action: str,
    ) -> None:
        if not self._provider:
            raise RuntimeError("GRAPH_DISABLED")
        await self._provider.project_case(
            case_id=case_id,
            case_version=case_version,
            device_type=device_type,
            alarm_name=alarm_name,
            fault_cause=fault_cause,
            resolution_action=resolution_action,
        )

    async def tombstone_case(self, case_id: str) -> None:
        if not self._provider:
            raise RuntimeError("GRAPH_DISABLED")
        await self._provider.tombstone_case(case_id)

    async def query(
        self,
        *,
        alarm_name: str,
        device_type: str | None,
        component: str | None,
        relation_depth: int,
        top_k: int,
    ) -> list[GraphRelation]:
        if not self._provider:
            raise RuntimeError("GRAPH_DISABLED")
        return await self._provider.query_relations(
            alarm_name=alarm_name,
            device_type=device_type,
            component=component,
            relation_depth=relation_depth,
            top_k=top_k,
        )
