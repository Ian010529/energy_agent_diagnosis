"""时序窗口 Mock Provider，返回摘要而不是大量原始点。"""

import json
from pathlib import Path
from typing import cast

from energy_agent_diagnosis.contracts import (
    ProviderType,
    ToolContext,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
from energy_agent_diagnosis.ports.providers import Payload, ProviderResult


class MockTimeseriesProvider:
    """按设备和指标读取预计算摘要，模拟阶段 2 时序数据接入。"""

    def __init__(self, data_path: Path | None = None) -> None:
        """允许测试注入路径；默认使用阶段 2 预计算时序摘要。"""
        self._data_path = (
            data_path or Path(__file__).parents[2] / "fixtures" / "timeseries" / "summaries.json"
        )

    async def query_timeseries_window(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回请求指标的窗口摘要，缺少部分指标时显式标记部分成功。"""
        device_id = payload.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            return self._not_found(context, "device_id 缺失或非法")

        requested_metrics = self._requested_metrics(payload)
        for record in self._load_records():
            if record.get("device_id") != device_id:
                continue
            metrics = self._filter_metrics(record, requested_metrics)
            if not metrics:
                return self._not_found(context, "未找到请求指标的时序摘要")

            missing = sorted(requested_metrics.difference(self._metric_names(metrics)))
            status = ToolStatus.PARTIAL_SUCCESS if missing else ToolStatus.OK
            data: Payload = {
                "device_id": device_id,
                "start_time": payload.get(
                    "start_time",
                    payload.get("start", record.get("start_time")),
                ),
                "end_time": payload.get("end_time", payload.get("end", record.get("end_time"))),
                "metrics": metrics,
                "data_completeness": record.get("data_completeness", 0.0),
                "missing_metrics": missing,
            }
            return ToolResult[Payload](
                success=True,
                status=status,
                data=data,
                meta=self._meta(context, partial_result=bool(missing)),
                warnings=[f"缺少指标: {', '.join(missing)}"] if missing else [],
            )
        return self._not_found(context, "未找到设备时序摘要")

    def _load_records(self) -> list[Payload]:
        """加载预计算摘要；Mock 阶段避免把海量点位塞给 Agent。"""
        raw: object = json.loads(self._data_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("timeseries fixture 必须是数组")

        records: list[Payload] = []
        for item in raw:
            if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
                raise ValueError("timeseries fixture 的每条记录必须是字符串键对象")
            records.append(cast(Payload, item))
        return records

    @staticmethod
    def _requested_metrics(payload: Payload) -> set[str]:
        """空指标列表表示返回该设备已有摘要，便于早期联调。"""
        raw_metrics = payload.get("metrics")
        if not isinstance(raw_metrics, list):
            return set()
        return {metric for metric in raw_metrics if isinstance(metric, str) and metric}

    @staticmethod
    def _filter_metrics(record: Payload, requested_metrics: set[str]) -> list[Payload]:
        """按请求指标裁剪摘要，保持工具返回体小而稳定。"""
        raw_metrics = record.get("metrics")
        if not isinstance(raw_metrics, list):
            return []
        metrics = [
            cast(Payload, item)
            for item in raw_metrics
            if isinstance(item, dict)
            and all(isinstance(key, str) for key in item)
            and (
                not requested_metrics
                or (
                    isinstance(item.get("metric_name"), str)
                    and item["metric_name"] in requested_metrics
                )
            )
        ]
        return metrics

    @staticmethod
    def _metric_names(metrics: list[Payload]) -> set[str]:
        """提取实际返回指标名，用于生成部分成功提示。"""
        return {name for metric in metrics if isinstance(name := metric.get("metric_name"), str)}

    @staticmethod
    def _meta(context: ToolContext, *, partial_result: bool = False) -> ToolMeta:
        """时序 Mock 使用 partial_result 区分完整摘要和部分指标缺失。"""
        return ToolMeta(
            trace_id=context.trace_id,
            source_system="stage2-fixture",
            provider_type=ProviderType.MOCK,
            partial_result=partial_result,
        )

    def _not_found(self, context: ToolContext, message: str) -> ProviderResult:
        """时序不可用时使用文档约定错误码，避免输出强诊断结论。"""
        return ToolResult[Payload](
            success=False,
            status=ToolStatus.NOT_FOUND,
            data={},
            meta=self._meta(context),
            error_code="TIMESERIES_UNAVAILABLE",
            error_message=message,
        )
