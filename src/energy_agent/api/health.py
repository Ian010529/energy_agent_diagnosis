import asyncio
from collections.abc import Awaitable
from typing import Literal

from fastapi import APIRouter, Request, Response

from energy_agent.contracts.common import StrictModel
from energy_agent.core.context import get_context
from energy_agent.persistence.mysql import mysql_ping
from energy_agent.persistence.redis import redis_ping

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(StrictModel):
    status: Literal["alive"]
    trace_id: str


class ReadyDependencies(StrictModel):
    mysql: Literal["up", "down"]
    redis: Literal["up", "down"]
    influxdb: Literal["up", "down"]
    minio: Literal["up", "down", "optional"]
    milvus: Literal["up", "down", "optional"]
    embedding: Literal["up", "down", "optional"]
    reranker: Literal["up", "down", "optional"]
    langfuse: Literal["optional"] = "optional"


class ReadyResponse(StrictModel):
    status: Literal["ready", "not_ready"]
    dependencies: ReadyDependencies
    capabilities: dict[str, Literal["ready", "degraded", "not_ready"]]
    trace_id: str


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    context = get_context()
    assert context is not None
    return LiveResponse(status="alive", trace_id=context.trace_id)


async def _dependency_status(
    check: Awaitable[object],
    *,
    timeout_seconds: float = 1.0,
) -> str:
    try:
        async with asyncio.timeout(timeout_seconds):
            await check
    except Exception:
        return "down"
    return "up"


@router.get("/ready", response_model=ReadyResponse)
async def ready(request: Request, response: Response) -> ReadyResponse:
    async def influx_status() -> object:
        healthy = await asyncio.to_thread(request.app.state.influx_client.ping)
        if not healthy:
            raise ConnectionError("InfluxDB ping failed")
        return healthy

    mysql, redis, influxdb = await asyncio.gather(
        _dependency_status(mysql_ping(request.app.state.mysql_engine)),
        _dependency_status(redis_ping(request.app.state.redis)),
        _dependency_status(influx_status()),
    )
    settings = request.app.state.settings
    if settings.retrieval_mode == "hybrid":
        minio, milvus, embedding = await asyncio.gather(
            _dependency_status(
                request.app.state.minio_provider.health(),
                timeout_seconds=3.0,
            ),
            _dependency_status(
                request.app.state.milvus_provider.health(),
                timeout_seconds=3.0,
            ),
            _dependency_status(
                request.app.state.embedding_provider.health(),
                timeout_seconds=min(settings.embedding_timeout_seconds, 10.0),
            ),
        )
    else:
        minio = milvus = embedding = "optional"
    reranker = (
        await _dependency_status(
            request.app.state.reranker_provider.health(),
            timeout_seconds=min(settings.rerank_timeout_seconds, 10.0),
        )
        if request.app.state.reranker_provider
        else "optional"
    )
    core = [mysql, redis, influxdb]
    if settings.retrieval_mode == "hybrid":
        core.extend([minio, milvus, embedding])
    status = "ready" if all(item == "up" for item in core) else "not_ready"
    if status == "not_ready":
        response.status_code = 503
    context = get_context()
    assert context is not None
    return ReadyResponse(
        status=status,
        dependencies=ReadyDependencies(
            mysql=mysql,
            redis=redis,
            influxdb=influxdb,
            minio=minio,
            milvus=milvus,
            embedding=embedding,
            reranker=reranker,
        ),
        capabilities={
            "diagnosis": "ready" if status == "ready" else "not_ready",
            "retrieval": (
                "ready"
                if settings.retrieval_mode == "hybrid"
                and all(item == "up" for item in (minio, milvus, embedding))
                else "degraded"
            ),
            "indexing": ("degraded" if settings.index_execution_mode == "rabbitmq" else "ready"),
            "graph": "ready" if settings.graph_mode == "neo4j" else "degraded",
        },
        trace_id=context.trace_id,
    )
