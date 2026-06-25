"""验证 readiness 对必需、可选、超时和 Redis 协议的处理。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from energy_agent_diagnosis.core.config import DependencyEndpoint, DependencySettings
from energy_agent_diagnosis.core.metrics import Metrics
from energy_agent_diagnosis.infrastructure.health import HealthService, ProbeStatus


@asynccontextmanager
async def tcp_server(*, redis: bool = False, port: int = 0) -> AsyncIterator[int]:
    """启动只供测试使用的临时 TCP 或 Redis PING 服务。"""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if redis:
            await reader.readline()
            await reader.readline()
            writer.write(b"+PONG\r\n")
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", port)
    port = server.sockets[0].getsockname()[1]
    try:
        yield int(port)
    finally:
        server.close()
        await server.wait_closed()


@asynccontextmanager
async def http_server(status_code: int) -> AsyncIterator[str]:
    """启动返回固定状态码的最小 HTTP 健康端点。"""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        response = f"HTTP/1.1 {status_code} Test\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        writer.write(response.encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = int(server.sockets[0].getsockname()[1])
    try:
        yield f"http://127.0.0.1:{port}/health"
    finally:
        server.close()
        await server.wait_closed()


def health_service(dependencies: DependencySettings, timeout: float = 0.2) -> HealthService:
    """创建具有独立指标注册表的测试健康服务。"""
    return HealthService(
        dependencies,
        timeout_seconds=timeout,
        metrics=Metrics("test_health"),
    )


@pytest.mark.asyncio
async def test_required_tcp_dependency_can_be_ready() -> None:
    async with tcp_server() as port:
        dependencies = DependencySettings(
            mysql=DependencyEndpoint(enabled=True, required=True, protocol="tcp", port=port)
        )
        report = await health_service(dependencies).check()

    assert report.status is ProbeStatus.READY
    assert report.dependencies[0].status is ProbeStatus.READY


@pytest.mark.asyncio
async def test_required_failure_blocks_readiness() -> None:
    dependencies = DependencySettings(
        mysql=DependencyEndpoint(enabled=True, required=True, protocol="tcp", port=1)
    )

    report = await health_service(dependencies).check()

    assert report.status is ProbeStatus.FAILED


@pytest.mark.asyncio
async def test_optional_failure_is_degraded() -> None:
    dependencies = DependencySettings(
        neo4j=DependencyEndpoint(enabled=True, required=False, protocol="tcp", port=1)
    )

    report = await health_service(dependencies).check()

    assert report.status is ProbeStatus.DEGRADED


@pytest.mark.asyncio
async def test_redis_probe_requires_pong() -> None:
    async with tcp_server(redis=True) as port:
        dependencies = DependencySettings(
            redis=DependencyEndpoint(enabled=True, required=True, protocol="redis", port=port)
        )
        report = await health_service(dependencies).check()

    assert report.status is ProbeStatus.READY


@pytest.mark.asyncio
async def test_disabled_dependencies_are_skipped() -> None:
    report = await health_service(DependencySettings()).check()

    assert report.status is ProbeStatus.READY
    assert report.dependencies == []


@pytest.mark.asyncio
async def test_probe_timeout_is_reported_without_internal_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependencies = DependencySettings(
        minio=DependencyEndpoint(
            enabled=True,
            required=True,
            protocol="http",
            url="http://dependency.invalid/health",
        )
    )
    service = health_service(dependencies, timeout=0.01)

    async def never_finishes(_endpoint: DependencyEndpoint) -> None:
        # 用可控协程模拟依赖卡死，验证外层统一超时而不依赖操作系统网络行为。
        await asyncio.sleep(1)

    monkeypatch.setattr(service, "_probe_http", never_finishes)
    report = await service.check()

    assert report.status is ProbeStatus.FAILED
    assert report.dependencies[0].message == "TimeoutError"


@pytest.mark.asyncio
async def test_dependency_can_recover_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    dependencies = DependencySettings(
        mysql=DependencyEndpoint(enabled=True, required=True, protocol="tcp", port=1)
    )
    service = health_service(dependencies)
    attempts = 0

    async def recover_on_second_probe(_endpoint: DependencyEndpoint) -> None:
        # 用确定性的状态切换验证同一服务实例不会缓存失败结果。
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("dependency unavailable")

    monkeypatch.setattr(service, "_probe_tcp", recover_on_second_probe)

    failed_report = await service.check()
    recovered_report = await service.check()

    assert failed_report.status is ProbeStatus.FAILED
    assert recovered_report.status is ProbeStatus.READY


@pytest.mark.asyncio
async def test_http_probe_rejects_wrong_health_path() -> None:
    async with http_server(404) as url:
        dependencies = DependencySettings(
            minio=DependencyEndpoint(
                enabled=True,
                required=True,
                protocol="http",
                url=url,
            )
        )
        report = await health_service(dependencies).check()

    assert report.status is ProbeStatus.FAILED
