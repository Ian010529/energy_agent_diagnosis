"""对启用的外部依赖执行有超时的真实网络探测。"""

import asyncio
from enum import StrEnum

import httpx
from pydantic import BaseModel, Field

from energy_agent_diagnosis.core.config import DependencyEndpoint, DependencySettings
from energy_agent_diagnosis.core.metrics import Metrics


class ProbeStatus(StrEnum):
    """单个依赖或整体 readiness 的状态。"""

    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"


class DependencyReport(BaseModel):
    """表示单个依赖的探测结论。"""

    name: str
    required: bool
    status: ProbeStatus
    message: str = ""


class ReadinessReport(BaseModel):
    """汇总应用所有已启用依赖的就绪状态。"""

    status: ProbeStatus
    dependencies: list[DependencyReport] = Field(default_factory=list)


class HealthService:
    """并发探测依赖，并将结果同步到 readiness 和 Prometheus。"""

    def __init__(
        self,
        dependencies: DependencySettings,
        *,
        timeout_seconds: float,
        metrics: Metrics,
    ) -> None:
        """保存探测配置引用和指标句柄；应用生命周期内不主动修改配置。"""
        self._dependencies = dependencies
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics

    async def check(self) -> ReadinessReport:
        """检查全部已启用依赖，并按 required 属性计算整体状态。"""
        configured = self._dependencies.enabled_items()
        reports = await asyncio.gather(
            *(self._probe(name, endpoint) for name, endpoint in configured)
        )
        required_failed = any(
            report.required and report.status is ProbeStatus.FAILED for report in reports
        )
        optional_failed = any(
            not report.required and report.status is ProbeStatus.FAILED for report in reports
        )
        status = (
            ProbeStatus.FAILED
            if required_failed
            else ProbeStatus.DEGRADED
            if optional_failed
            else ProbeStatus.READY
        )
        return ReadinessReport(status=status, dependencies=list(reports))

    async def _probe(self, name: str, endpoint: DependencyEndpoint) -> DependencyReport:
        """执行单个协议探测，并把异常收敛成不泄漏凭据的状态。"""
        try:
            async with asyncio.timeout(self._timeout_seconds):
                if endpoint.protocol == "http":
                    await self._probe_http(endpoint)
                elif endpoint.protocol == "redis":
                    await self._probe_redis(endpoint)
                else:
                    await self._probe_tcp(endpoint)
        except (TimeoutError, OSError, httpx.HTTPError) as exc:
            self._metrics.set_dependency_health(name, required=endpoint.required, healthy=False)
            return DependencyReport(
                name=name,
                required=endpoint.required,
                status=ProbeStatus.FAILED,
                message=type(exc).__name__,
            )
        self._metrics.set_dependency_health(name, required=endpoint.required, healthy=True)
        return DependencyReport(
            name=name,
            required=endpoint.required,
            status=ProbeStatus.READY,
        )

    async def _probe_tcp(self, endpoint: DependencyEndpoint) -> None:
        """建立并立即关闭 TCP 连接，验证端口真实可达。"""
        if endpoint.port is None:
            raise OSError("missing port")
        _reader, writer = await asyncio.open_connection(endpoint.host, endpoint.port)
        writer.close()
        await writer.wait_closed()

    async def _probe_http(self, endpoint: DependencyEndpoint) -> None:
        """调用依赖健康 URL；只有 2xx 才证明目标路径真实可用。"""
        if endpoint.url is None:
            raise OSError("missing url")
        # 健康端点是显式配置的内部地址，不应被宿主 HTTP_PROXY 意外改道。
        async with httpx.AsyncClient(timeout=self._timeout_seconds, trust_env=False) as client:
            response = await client.get(endpoint.url)
            if not 200 <= response.status_code < 300:
                raise httpx.HTTPStatusError(
                    "dependency returned server error",
                    request=response.request,
                    response=response,
                )

    async def _probe_redis(self, endpoint: DependencyEndpoint) -> None:
        """发送 Redis PING，避免把普通 TCP 可达误判为协议健康。"""
        if endpoint.port is None:
            raise OSError("missing port")
        reader, writer = await asyncio.open_connection(endpoint.host, endpoint.port)
        try:
            writer.write(b"*1\r\n$4\r\nPING\r\n")
            await writer.drain()
            response = await reader.readline()
            if response.strip() != b"+PONG":
                raise OSError("unexpected redis response")
        finally:
            writer.close()
            await writer.wait_closed()
