"""手册 chunk 真实检索 Provider，通过 HTTP 请求远程服务实现检索。"""

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


class RealManualSearchProvider:
    """真实手册检索 Provider，访问外部 HTTP 接口并归一化输出。"""

    def __init__(self, endpoint: str, client: httpx.AsyncClient | None = None) -> None:
        """保存手册检索 endpoint，并允许测试注入 HTTP client。"""
        self.endpoint = endpoint
        self.client = client

    async def search_manual_chunks(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """调用真实外部手册检索接口。"""
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
                data={"chunks": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="manual-search-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="TIMEOUT",
                error_message=f"Timeout connecting to manual search endpoint: {exc}",
            )
        except Exception as exc:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.FAILED,
                data={"chunks": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="manual-search-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="SYSTEM_ERROR",
                error_message=f"Failed to query manual search endpoint: {exc}",
            )

        if response.status_code != 200:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.FAILED,
                data={"chunks": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="manual-search-real",
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
                data={"chunks": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="manual-search-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="SYSTEM_ERROR",
                error_message=f"Failed to parse JSON response: {exc}",
            )

        if isinstance(res_data, list):
            chunks = res_data
        elif isinstance(res_data, dict):
            chunks = res_data.get("chunks", [])
            if not isinstance(chunks, list):
                chunks = []
        else:
            chunks = []

        normalized_chunks = []
        for raw_chunk in chunks:
            if not isinstance(raw_chunk, dict):
                continue
            chunk = dict(raw_chunk)
            chunk.setdefault("source_type", "manual")
            if "score" in chunk:
                try:
                    chunk["score"] = float(chunk["score"])
                except (ValueError, TypeError):
                    chunk["score"] = 0.0
            else:
                chunk["score"] = 1.0
            normalized_chunks.append(chunk)

        if not normalized_chunks:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.NOT_FOUND,
                data={"chunks": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="manual-search-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="RETRIEVAL_FAILED",
                error_message="No matching manual chunks found",
            )

        return ToolResult[Payload](
            success=True,
            status=ToolStatus.OK,
            data={"chunks": normalized_chunks, "count": len(normalized_chunks)},
            meta=ToolMeta(
                trace_id=context.trace_id,
                source_system="manual-search-real",
                provider_type=ProviderType.REAL,
            ),
        )


async def _maybe_await(value: Any) -> Any:
    """兼容真实 httpx.Response 和测试中的 AsyncMock response。"""
    if inspect.isawaitable(value):
        return await value
    return value
