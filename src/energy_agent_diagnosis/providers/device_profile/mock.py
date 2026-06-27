"""设备画像 Mock Provider，用本地台账样例验证阶段 2 数据接入契约。"""

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


class MockDeviceProfileProvider:
    """从运行期 fixture 查询设备画像，不让上层感知数据来自 JSON。"""

    def __init__(self, data_path: Path | None = None) -> None:
        """允许测试注入路径；默认读取包内阶段 2 Mock 数据资产。"""
        self._data_path = data_path or Path(__file__).parents[2] / "fixtures" / "devices.json"

    async def get_device_profile(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """按 ``device_id`` 返回标准设备画像，找不到时给稳定错误码。"""
        device_id = payload.get("device_id")
        if not isinstance(device_id, str) or not device_id:
            return self._not_found(context, "")

        for record in self._load_records():
            if record.get("device_id") == device_id:
                return ToolResult[Payload](
                    success=True,
                    status=ToolStatus.OK,
                    data=record,
                    meta=self._meta(context),
                )
        return self._not_found(context, device_id)

    def _load_records(self) -> list[Payload]:
        """加载并轻量校验 fixture，避免把坏 JSON 当作业务空结果吞掉。"""
        raw: object = json.loads(self._data_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("devices fixture 必须是数组")

        records: list[Payload] = []
        for item in raw:
            if not isinstance(item, dict) or not all(isinstance(key, str) for key in item):
                raise ValueError("devices fixture 的每条记录必须是字符串键对象")
            records.append(cast(Payload, item))
        return records

    @staticmethod
    def _meta(context: ToolContext) -> ToolMeta:
        """Mock 也透传 trace，保证后续 Real Adapter 可以复用同一观测契约。"""
        return ToolMeta(
            trace_id=context.trace_id,
            source_system="stage2-fixture",
            provider_type=ProviderType.MOCK,
        )

    def _not_found(self, context: ToolContext, device_id: str) -> ProviderResult:
        """统一设备未找到语义，调用方不需要解析异常文本。"""
        message = "设备不存在" if device_id else "device_id 缺失或非法"
        return ToolResult[Payload](
            success=False,
            status=ToolStatus.NOT_FOUND,
            data={},
            meta=self._meta(context),
            error_code="DEVICE_NOT_FOUND",
            error_message=message,
        )
