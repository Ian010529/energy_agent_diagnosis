from typing import cast

from pydantic import BaseModel

from energy_agent.graph.service import GraphService
from energy_agent.observability.tracing import Tracer
from energy_agent.tools.contracts import (
    GraphRelationsInput,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
from energy_agent.tools.registry import ToolRegistry


def register_graph_tool(
    registry: ToolRegistry,
    graph: GraphService,
    tracer: Tracer | None = None,
) -> None:
    async def query(payload: BaseModel) -> ToolResult:
        request = cast(GraphRelationsInput, payload)
        try:
            if tracer:
                with tracer.start_span(
                    "graph.query",
                    trace_id=request.context.trace_id,
                    metadata={
                        "alarm_name": request.alarm_name,
                        "relation_depth": request.relation_depth,
                        "top_k": request.top_k,
                    },
                ):
                    relations = await graph.query(
                        alarm_name=request.alarm_name,
                        device_type=request.device_type,
                        component=request.component,
                        relation_depth=request.relation_depth,
                        top_k=request.top_k,
                    )
            else:
                relations = await graph.query(
                    alarm_name=request.alarm_name,
                    device_type=request.device_type,
                    component=request.component,
                    relation_depth=request.relation_depth,
                    top_k=request.top_k,
                )
        except Exception as exc:
            error_code = "GRAPH_DISABLED" if str(exc) == "GRAPH_DISABLED" else "GRAPH_UNAVAILABLE"
            return ToolResult(
                success=False,
                status=ToolStatus.DEGRADED,
                data={"relations": []},
                meta=ToolMeta(
                    trace_id=request.context.trace_id,
                    source_system="neo4j",
                    partial_result=True,
                ),
                error_code=error_code,
                error_message="Graph relation evidence is unavailable",
                warnings=[error_code],
            )
        if not relations:
            return ToolResult(
                success=False,
                status=ToolStatus.NOT_FOUND,
                data={"relations": []},
                meta=ToolMeta(
                    trace_id=request.context.trace_id,
                    source_system="neo4j",
                ),
                error_code="GRAPH_RELATIONS_NOT_FOUND",
                error_message="No graph relations found",
            )
        return ToolResult(
            success=True,
            status=ToolStatus.OK,
            data={"relations": [item.model_dump(mode="json") for item in relations]},
            meta=ToolMeta(
                trace_id=request.context.trace_id,
                source_system="neo4j",
            ),
        )

    registry.register("query_graph_relations", GraphRelationsInput, query)
