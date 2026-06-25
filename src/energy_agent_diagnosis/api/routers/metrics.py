"""暴露 Prometheus 文本指标。"""

from typing import cast

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST

from energy_agent_diagnosis.core.metrics import Metrics


def build_metrics_router(path: str) -> APIRouter:
    """按配置路径创建指标路由，避免声明了配置却仍硬编码。"""
    router = APIRouter(tags=["metrics"])

    @router.get(path, include_in_schema=False)
    async def metrics(request: Request) -> Response:
        """返回应用实例的低基数指标注册表。"""
        application_metrics = cast(Metrics, request.app.state.metrics)
        return Response(application_metrics.render(), media_type=CONTENT_TYPE_LATEST)

    return router
