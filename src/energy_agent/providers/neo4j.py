import asyncio

from neo4j import AsyncGraphDatabase

from energy_agent.graph.contracts import GraphRelation


class Neo4jProvider:
    provider_type = "real"

    def __init__(
        self,
        *,
        uri: str,
        user: str,
        password: str,
        database: str,
        timeout_seconds: float,
    ) -> None:
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        self.database = database
        self.timeout_seconds = timeout_seconds

    async def verify(self) -> None:
        await self.driver.verify_connectivity()

    async def ensure_schema(self) -> None:
        labels = ("DeviceType", "Component", "Alarm", "FaultCause", "Action", "Case")
        async with self.driver.session(database=self.database) as session:
            for label in labels:
                await session.run(
                    f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
                    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                )

    async def project_template(self, payload: dict[str, object]) -> None:
        query = """
        MERGE (d:DeviceType {id: $device_type})
        MERGE (a:Alarm {id: $alarm_id})
        SET a.name = $alarm_name
        MERGE (d)-[:HAS_ALARM {source_type: 'template', source_id: $template_id,
                               source_version: $template_version}]->(a)
        WITH a
        UNWIND $relations AS rel
        MERGE (f:FaultCause {id: rel.fault_cause})
        SET f.name = rel.fault_cause
        MERGE (c:Component {id: rel.component})
        SET c.name = rel.component
        MERGE (a)-[:MAY_BE_CAUSED_BY {source_type: 'template', source_id: $template_id,
                                     source_version: $template_version}]->(f)
        MERGE (f)-[:RELATES_TO {source_type: 'template', source_id: $template_id,
                               source_version: $template_version}]->(c)
        FOREACH (action_name IN rel.actions |
          MERGE (x:Action {id: action_name})
          SET x.name = action_name
          MERGE (f)-[:MITIGATED_BY {source_type: 'template', source_id: $template_id,
                                    source_version: $template_version}]->(x))
        """
        await self._write(query, payload)

    async def project_case(self, *, case_id: str, case_version: int, fault_cause: str) -> None:
        await self._write(
            """
            MERGE (c:Case {id: $case_id})
            SET c.version = $case_version, c.active = true
            MERGE (f:FaultCause {id: $fault_cause})
            SET f.name = $fault_cause
            MERGE (c)-[r:CONFIRMS]->(f)
            SET r.case_id = $case_id, r.case_version = $case_version, r.active = true
            """,
            {
                "case_id": case_id,
                "case_version": case_version,
                "fault_cause": fault_cause,
            },
        )

    async def tombstone_case(self, case_id: str) -> None:
        await self._write(
            "MATCH (c:Case {id: $case_id}) DETACH DELETE c",
            {"case_id": case_id},
        )

    async def query_relations(
        self,
        *,
        alarm_name: str,
        device_type: str | None,
        component: str | None,
        relation_depth: int,
        top_k: int,
    ) -> list[GraphRelation]:
        del relation_depth
        query = """
        MATCH (d:DeviceType)-[da:HAS_ALARM]->(a:Alarm)-[af:MAY_BE_CAUSED_BY]->(f:FaultCause)
        OPTIONAL MATCH (f)-[:RELATES_TO]->(c:Component)
        OPTIONAL MATCH (f)-[:MITIGATED_BY]->(x:Action)
        OPTIONAL MATCH (support:Case)-[sc:CONFIRMS {active: true}]->(f)
        WHERE (toLower(a.name) CONTAINS toLower($alarm_name) OR
               toLower(a.id) CONTAINS toLower($alarm_name))
          AND ($device_type IS NULL OR d.id = $device_type)
          AND ($component IS NULL OR c.id = $component OR c.name = $component)
        RETURN a.name AS alarm_name, f.name AS fault_cause, c.name AS component,
               collect(DISTINCT x.name) AS actions,
               collect(DISTINCT support.id) AS support_case_ids,
               count(DISTINCT support) AS support_count,
               collect(DISTINCT af.source_id) AS template_ids
        ORDER BY support_count DESC, fault_cause
        LIMIT $top_k
        """
        async with self.driver.session(database=self.database) as session:
            async with asyncio.timeout(self.timeout_seconds):
                result = await session.run(
                    query,
                    alarm_name=alarm_name,
                    device_type=device_type,
                    component=component,
                    top_k=top_k,
                )
                rows = [record.data() async for record in result]
        return [GraphRelation.model_validate(row) for row in rows]

    async def _write(self, query: str, parameters: dict[str, object]) -> None:
        async with self.driver.session(database=self.database) as session:
            async with asyncio.timeout(self.timeout_seconds):
                await session.run(query, dict(parameters))

    async def close(self) -> None:
        await self.driver.close()
