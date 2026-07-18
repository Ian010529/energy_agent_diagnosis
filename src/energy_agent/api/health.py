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
    trace_id: str


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    context = get_context()
    assert context is not None
    return LiveResponse(status="alive", trace_id=context.trace_id)


async def _dependency_status(check: Awaitable[object]) -> str:
    try:
        async with asyncio.timeout(1.0):
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
            _dependency_status(request.app.state.minio_provider.health()),
            _dependency_status(request.app.state.milvus_provider.health()),
            _dependency_status(request.app.state.embedding_provider.health()),
        )
    else:
        minio = milvus = embedding = "optional"
    reranker = (
        await _dependency_status(request.app.state.reranker_provider.health())
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
        trace_id=context.trace_id,
    )
