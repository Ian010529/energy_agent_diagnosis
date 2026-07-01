"""检索用外部 LLM 改写和重排服务的外部调用端口。"""

import inspect
from typing import Any, cast

import httpx


async def call_qwen_rewrite(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """调用 Qwen 外部重写接口并返回结果字典。"""
    try:
        if client is not None:
            response = await client.post(endpoint, json=payload, headers=headers, timeout=5.0)
        else:
            async with httpx.AsyncClient() as c:
                response = await c.post(endpoint, json=payload, headers=headers, timeout=5.0)
        await _maybe_await(response.raise_for_status())
        data = await _maybe_await(response.json())
        if not isinstance(data, dict):
            return {}
        return cast(dict[str, Any], data)
    except httpx.TimeoutException as exc:
        raise TimeoutError(str(exc)) from exc


async def call_reranker(
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    client: httpx.AsyncClient | None = None,
) -> Any:
    """调用外部 Reranker 并返回得分列表或结构。"""
    try:
        if client is not None:
            response = await client.post(endpoint, json=payload, headers=headers, timeout=5.0)
        else:
            async with httpx.AsyncClient() as c:
                response = await c.post(endpoint, json=payload, headers=headers, timeout=5.0)
        await _maybe_await(response.raise_for_status())
        data = response.json()
        return await _maybe_await(data)
    except httpx.TimeoutException as exc:
        raise TimeoutError(str(exc)) from exc


async def _maybe_await(value: Any) -> Any:
    """兼容真实 httpx.Response 和测试中的 AsyncMock response。"""
    if inspect.isawaitable(value):
        return await value
    return value
