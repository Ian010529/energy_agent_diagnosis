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
        await self._write(
            """
            OPTIONAL MATCH ()-[old]->()
            WHERE (old.source_type = 'case' AND old.source_id = $case_id)
               OR (type(old) = 'CONFIRMS' AND old.case_id = $case_id)
            WITH collect(old) AS old_relations
            FOREACH (old IN old_relations | DELETE old)
            WITH 1 AS projection
            MERGE (d:DeviceType {id: $device_type})
            WITH d
            MATCH (d)-[:HAS_ALARM {source_type: 'template'}]->(a:Alarm)
            WHERE toLower($alarm_name) CONTAINS toLower(a.name)
               OR toLower(a.name) CONTAINS toLower($alarm_name)
            WITH d, a ORDER BY size(a.name) DESC LIMIT 1
            MERGE (c:Case {id: $case_id})
            SET c.version = $case_version, c.active = true
            MERGE (f:FaultCause {id: $fault_cause})
            SET f.name = $fault_cause
            MERGE (x:Action {id: $resolution_action})
            SET x.name = $resolution_action
            MERGE (c)-[cf:CONFIRMS {source_type: 'case', source_id: $case_id}]->(f)
            SET cf.source_version = $case_version, cf.case_id = $case_id,
                cf.case_version = $case_version, cf.active = true
            MERGE (d)-[da:HAS_ALARM {source_type: 'case', source_id: $case_id}]->(a)
            SET da.source_version = $case_version, da.active = true
            MERGE (a)-[af:MAY_BE_CAUSED_BY {source_type: 'case',
                                            source_id: $case_id}]->(f)
            SET af.source_version = $case_version, af.active = true
            MERGE (f)-[fx:MITIGATED_BY {source_type: 'case',
                                        source_id: $case_id}]->(x)
            SET fx.source_version = $case_version, fx.active = true
            """,
            {
                "case_id": case_id,
                "case_version": case_version,
                "device_type": device_type,
                "alarm_name": alarm_name,
                "fault_cause": fault_cause,
                "resolution_action": resolution_action,
            },
        )

    async def tombstone_case(self, case_id: str) -> None:
        await self._write(
            """
            OPTIONAL MATCH ()-[case_relation]->()
            WHERE (case_relation.source_type = 'case'
                   AND case_relation.source_id = $case_id)
               OR (type(case_relation) = 'CONFIRMS'
                   AND case_relation.case_id = $case_id)
            WITH collect(case_relation) AS case_relations
            FOREACH (relation IN case_relations | DELETE relation)
            WITH 1 AS tombstone
            OPTIONAL MATCH (c:Case {id: $case_id})
            WITH collect(c) AS cases
            FOREACH (case_node IN cases | DETACH DELETE case_node)
            WITH 1 AS cleanup
            OPTIONAL MATCH (orphan)
            WHERE (orphan:Action OR orphan:FaultCause) AND NOT (orphan)--()
            WITH collect(orphan) AS orphans
            FOREACH (orphan IN orphans | DELETE orphan)
            """,
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
               toLower($alarm_name) CONTAINS toLower(a.name) OR
               toLower(a.id) CONTAINS toLower($alarm_name))
          AND ($device_type IS NULL OR d.id = $device_type)
          AND ($component IS NULL OR c.id = $component OR c.name = $component)
        RETURN a.name AS alarm_name, f.name AS fault_cause, c.name AS component,
               collect(DISTINCT x.name)[0..10] AS actions,
               collect(DISTINCT support.id) AS support_case_ids,
               count(DISTINCT support) AS support_count,
               [source_id IN collect(
                 DISTINCT CASE WHEN af.source_type = 'template' THEN af.source_id END
               ) WHERE source_id IS NOT NULL] AS template_ids
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
