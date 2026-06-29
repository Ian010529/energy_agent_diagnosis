"""工单写入 Mock Provider，只生成受控草稿或模拟编号。"""

from hashlib import sha256

from energy_agent_diagnosis.contracts import (
    ProviderType,
    ToolContext,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
from energy_agent_diagnosis.ports.providers import Payload, ProviderResult


class MockTicketWriteProvider:
    """模拟工单创建或更新结果；显式确认门禁由 Tool 层负责。"""

    async def create_or_update_ticket(
        self,
        context: ToolContext,
        payload: Payload,
    ) -> ProviderResult:
        """返回可追溯的工单草稿或模拟工单号。"""
        action = payload.get("action")
        device_id = payload.get("device_id")
        summary = payload.get("summary")
        if action not in {"create", "update"}:
            return self._failed(context, "INVALID_TOOL_ARGUMENT", "action 必须是 create 或 update")
        if not isinstance(device_id, str) or not device_id:
            return self._failed(context, "INVALID_TOOL_ARGUMENT", "device_id 缺失或非法")
        if not isinstance(summary, str) or not summary.strip():
            return self._failed(context, "INVALID_TOOL_ARGUMENT", "summary 缺失或非法")

        simulated_id = self._stable_ticket_id(action, device_id, summary)
        data: Payload = {
            "ticket_id": simulated_id,
            "action": action,
            "device_id": device_id,
            "summary": summary,
            "status": "DRAFT",
            "draft": True,
            "submitted": False,
            "source_type": "ticket_write",
        }
        return ToolResult[Payload](
            success=True,
            status=ToolStatus.OK,
            data=data,
            meta=self._meta(context),
            warnings=["Mock Provider 不会写入真实工单系统"],
        )

    @staticmethod
    def _stable_ticket_id(action: object, device_id: str, summary: str) -> str:
        """根据输入生成稳定模拟编号，避免测试依赖随机数。"""
        digest = sha256(f"{action}:{device_id}:{summary}".encode()).hexdigest()[:8].upper()
        return f"MOCK-TICKET-{digest}"

    @staticmethod
    def _meta(context: ToolContext) -> ToolMeta:
        """工单写入 Mock 也保留标准观测元数据。"""
        return ToolMeta(
            trace_id=context.trace_id,
            source_system="stage2-fixture",
            provider_type=ProviderType.MOCK,
        )

    def _failed(self, context: ToolContext, error_code: str, message: str) -> ProviderResult:
        """返回稳定失败结构，不抛出业务异常。"""
        return ToolResult[Payload](
            success=False,
            status=ToolStatus.FAILED,
            data={},
            meta=self._meta(context),
            error_code=error_code,
            error_message=message,
        )
