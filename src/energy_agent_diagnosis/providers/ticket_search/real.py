"""历史工单真实检索 Provider，通过 HTTP 请求远程服务实现检索。"""

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


class RealTicketSearchProvider:
    """真实工单检索 Provider，访问外部 HTTP 接口并归一化输出。"""

    def __init__(self, endpoint: str, client: httpx.AsyncClient | None = None) -> None:
        """保存工单检索 endpoint，并允许测试注入 HTTP client。"""
        self.endpoint = endpoint
        self.client = client

    async def search_similar_tickets(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """调用真实外部工单检索接口。"""
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
                data={"tickets": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="ticket-search-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="TIMEOUT",
                error_message=f"Timeout connecting to ticket search endpoint: {exc}",
            )
        except Exception as exc:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.FAILED,
                data={"tickets": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="ticket-search-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="SYSTEM_ERROR",
                error_message=f"Failed to query ticket search endpoint: {exc}",
            )

        if response.status_code != 200:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.FAILED,
                data={"tickets": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="ticket-search-real",
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
                data={"tickets": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="ticket-search-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="SYSTEM_ERROR",
                error_message=f"Failed to parse JSON response: {exc}",
            )

        if isinstance(res_data, list):
            tickets = res_data
        elif isinstance(res_data, dict):
            tickets = res_data.get("tickets", [])
            if not isinstance(tickets, list):
                tickets = []
        else:
            tickets = []

        normalized_tickets = []
        for raw_ticket in tickets:
            if not isinstance(raw_ticket, dict):
                continue
            ticket = dict(raw_ticket)
            ticket.setdefault("source_type", "ticket")

            is_verified = ticket.get("is_verified")
            if not isinstance(is_verified, bool):
                is_verified = False
            ticket["is_verified"] = is_verified
            ticket.setdefault("weak_evidence", not is_verified)

            if "score" in ticket:
                try:
                    ticket["score"] = float(ticket["score"])
                except (ValueError, TypeError):
                    ticket["score"] = 0.0
            else:
                ticket["score"] = 1.0
            normalized_tickets.append(ticket)

        if not normalized_tickets:
            return ToolResult[Payload](
                success=False,
                status=ToolStatus.NOT_FOUND,
                data={"tickets": [], "count": 0},
                meta=ToolMeta(
                    trace_id=context.trace_id,
                    source_system="ticket-search-real",
                    provider_type=ProviderType.REAL,
                ),
                error_code="RETRIEVAL_FAILED",
                error_message="No matching tickets found",
            )

        return ToolResult[Payload](
            success=True,
            status=ToolStatus.OK,
            data={"tickets": normalized_tickets, "count": len(normalized_tickets)},
            meta=ToolMeta(
                trace_id=context.trace_id,
                source_system="ticket-search-real",
                provider_type=ProviderType.REAL,
            ),
        )


async def _maybe_await(value: Any) -> Any:
    """兼容真实 httpx.Response 和测试中的 AsyncMock response。"""
    if inspect.isawaitable(value):
        return await value
    return value
