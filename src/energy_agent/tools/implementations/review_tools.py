from typing import cast

from pydantic import BaseModel

from energy_agent.cases.review_recorder import DiagnosisReviewRecorder
from energy_agent.tools.contracts import (
    AppendCaseReviewInput,
    ToolMeta,
    ToolResult,
    ToolStatus,
)
from energy_agent.tools.registry import ToolRegistry


def register_review_tool(registry: ToolRegistry, recorder: DiagnosisReviewRecorder) -> None:
    async def append(payload: BaseModel) -> ToolResult:
        request = cast(AppendCaseReviewInput, payload)
        record = await recorder.append(request)
        return ToolResult(
            success=True,
            status=ToolStatus.OK,
            data={
                "review_id": record.review_id,
                "created_at": record.created_at.isoformat(),
            },
            meta=ToolMeta(
                trace_id=request.context.trace_id,
                source_system="mysql",
            ),
        )

    registry.register(
        "append_case_review",
        AppendCaseReviewInput,
        append,
        read_only=False,
        requires_human_action=True,
    )
