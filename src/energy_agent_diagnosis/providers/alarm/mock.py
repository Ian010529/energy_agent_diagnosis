"""告警详情 Mock Provider，用本地告警事件样例验证阶段 2 接入契约。"""

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


class MockAlarmProvider:
    """按告警 ID 查询标准告警上下文，屏蔽 fixture 存储形态。"""

    def __init__(self, data_path: Path | None = None) -> None:
        """允许测试替换数据路径，默认读取阶段 2 告警样例。"""
        self._data_path = data_path or Path(__file__).parents[2] / "fixtures" / "alarms.json"

    async def get_alarm_detail(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """按 ``alarm_id`` 返回告警详情，并保留 ``alarm_time`` 兼容字段。"""
        alarm_id = payload.get("alarm_id")
        if not isinstance(alarm_id, str) or not alarm_id:
            return self._not_found(context, "")

        for record in self._load_records():
            if record.get("alarm_id") == alarm_id:
                data = dict(record)
                # 详细设计允许 alarm_time/trigger_time 互为别名；Mock 阶段就固定兼容。
                data.setdefault("alarm_time", data.get("trigger_time"))
                return ToolResult[Payload](
                    success=True,
                    status=ToolStatus.OK,
                    data=data,
                    meta=self._meta(context),
                )
        return self._not_found(context, alarm_id)

    def _load_records(self) -> list[Payload]:
        """加载告警 fixture，并在文件结构错误时快速失败。"""
        raw: object = json.loads(self._data_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("alarms fixture 必须是数组")

        records: list[Payload] = []
        for item in raw:
            if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
                raise ValueError("alarms fixture 的每条记录必须是字符串键对象")
            records.append(cast(Payload, item))
        return records

    @staticmethod
    def _meta(context: ToolContext) -> ToolMeta:
        """告警 Mock 也返回标准来源元数据，便于契约测试复用于 Real。"""
        return ToolMeta(
            trace_id=context.trace_id,
            source_system="stage2-fixture",
            provider_type=ProviderType.MOCK,
        )

    def _not_found(self, context: ToolContext, alarm_id: str) -> ProviderResult:
        """统一告警未找到语义，避免调用方依赖 fixture 细节。"""
        message = "告警不存在" if alarm_id else "alarm_id 缺失或非法"
        return ToolResult[Payload](
            success=False,
            status=ToolStatus.NOT_FOUND,
            data={},
            meta=self._meta(context),
            error_code="ALARM_NOT_FOUND",
            error_message=message,
        )
