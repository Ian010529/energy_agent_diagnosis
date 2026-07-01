"""图谱关系真实检索 Provider，通过 HTTP 请求远程服务实现关系查询。"""

import inspect
from typing import Any

import httpx

from energy_agent_diagnosis.contracts import (
    ProviderType,
    ToolContext,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
from energy_agent_diagnosis.ports.providers import Payload, ProviderResult


class RealGraphRelationProvider:
    """真实图谱关系 Provider，访问外部 HTTP 接口并归一化输出。"""

    def __init__(self, endpoint: str, client: httpx.AsyncClient | None = None) -> None:
        """保存图谱查询 endpoint，并允许测试注入 HTTP client。"""
        self.endpoint = endpoint
        self.client = client

    async def query_graph_relations(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """调用真实外部图谱关系查询接口。"""
        headers = {"x-trace-id": context.trace_id}

        try:
            if self.client is not None:
                response = await self.client.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                    timeout=10.0,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.endpoint,
                        json=payload,
                        headers=headers,
                        timeout=10.0,
                    )
        except httpx.TimeoutException as exc:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.TIMEOUT,
                data={"relations": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="graph-relation-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="TIMEOUT",
                error_message=f"Timeout connecting to graph relation endpoint: {exc}",
            )
        except Exception as exc:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.FAILED,
                data={"relations": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="graph-relation-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="SYSTEM_ERROR",
                error_message=f"Failed to query graph relation endpoint: {exc}",
            )

        if response.status_code != 200:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.FAILED,
                data={"relations": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="graph-relation-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="SYSTEM_ERROR",
                error_message=f"HTTP status code {response.status_code}: {response.text}",
            )

        try:
            res_data = await _maybe_await(response.json())
        except Exception as exc:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.FAILED,
                data={"relations": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="graph-relation-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="SYSTEM_ERROR",
                error_message=f"Failed to parse JSON response: {exc}",
            )

        if isinstance(res_data, list):
            relations = res_data
        elif isinstance(res_data, dict):
            relations = res_data.get("relations", [])
            if not isinstance(relations, list):
                relations = []
        else:
            relations = []

        normalized_relations = []
        for raw_rel in relations:
            if not isinstance(raw_rel, dict):
                continue
            rel = dict(raw_rel)
            rel.setdefault("source_type", "graph")
            rel.setdefault("weak_evidence", True)

            if "score" in rel:
                try:
                    rel["score"] = float(rel["score"])
                except (ValueError, TypeError):
                    rel["score"] = 0.0
            else:
                rel["score"] = 1.0
            normalized_relations.append(rel)

        if not normalized_relations:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.NOT_FOUND,
                data={"relations": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="graph-relation-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="GRAPH_RELATION_NOT_FOUND",
                error_message="No matching graph relations found",
            )

        return ToolResult[Payload](
            success=True,
            status=ToolStatus.OK,
            data={"relations": normalized_relations, "count": len(normalized_relations)},
            meta=ToolMeta(
                trace_id=context.trace_id,
                source_system="graph-relation-real",
                provider_type=ProviderType.REAL,
            ),
        )


async def _maybe_await(value: Any) -> Any:
    """兼容真实 httpx.Response 和测试中的 AsyncMock response。"""
    if inspect.isawaitable(value):
        return await value
    return value
