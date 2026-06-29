"""案例审核 Mock Provider，模拟审核记录和状态流转。"""

from hashlib import sha256

from energy_agent_diagnosis.contracts import (
    ProviderType,
    ToolContext,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
from energy_agent_diagnosis.ports.providers import Payload, ProviderResult


class MockCaseReviewProvider:
    """生成审核记录，不写入真实案例库或索引。"""

    async def append_case_review(self, context: ToolContext, payload: Payload) -> ProviderResult:
        """返回基于输入确定生成的审核记录。"""
        session_id = payload.get("session_id")
        review_result = payload.get("review_result")
        reviewer = payload.get("reviewer")
        if not isinstance(session_id, str) or not session_id:
            return self._failed(context, "INVALID_TOOL_ARGUMENT", "session_id 缺失或非法")
        if review_result not in {"confirmed", "rejected", "needs_more_info"}:
            return self._failed(context, "INVALID_TOOL_ARGUMENT", "review_result 非法")
        if not isinstance(reviewer, str) or not reviewer:
            return self._failed(context, "INVALID_TOOL_ARGUMENT", "reviewer 缺失或非法")

        review_id = self._stable_review_id(session_id, reviewer, review_result)
        case_status = {
            "confirmed": "APPROVED",
            "rejected": "REJECTED",
            "needs_more_info": "PENDING_REVIEW",
        }[review_result]
        data: Payload = {
            "review_id": review_id,
            "session_id": session_id,
            "review_result": review_result,
            "reviewer": reviewer,
            "case_status": case_status,
            "root_cause": payload.get("root_cause", ""),
            "comments": payload.get("comments", ""),
            "reviewed_at": "2026-06-26T00:00:00+00:00",
            "source_type": "case_review",
        }
        return ToolResult[Payload](
            success=True,
            status=ToolStatus.OK,
            data=data,
            meta=self._meta(context),
            warnings=["Mock Provider 不会写入真实案例库"],
        )

    @staticmethod
    def _stable_review_id(session_id: str, reviewer: str, review_result: object) -> str:
        """根据审核主键字段生成稳定记录编号。"""
        digest = sha256(f"{session_id}:{reviewer}:{review_result}".encode()).hexdigest()[:8].upper()
        return f"MOCK-REVIEW-{digest}"

    @staticmethod
    def _meta(context: ToolContext) -> ToolMeta:
        """案例审核 Mock 也保留标准观测元数据。"""
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
