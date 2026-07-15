"""ToolResult contract and its explicit legacy read adapter."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from energy_agent.contracts.common import StrictModel, ToolStatus, UUIDv7String


class ToolMeta(StrictModel):
    trace_id: UUIDv7String
    source_system: str
    provider_type: str
    partial_result: bool = False
    latency_ms: int = Field(ge=0)
    attempts: int = Field(default=1, ge=1)
    retryable: bool = False
    retry_after_seconds: int | None = Field(default=None, ge=0)


class ToolError(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ToolResult(StrictModel):
    status: ToolStatus
    success: bool
    data: Any | None
    meta: ToolMeta
    error: ToolError | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result_semantics(self) -> ToolResult:
        if self.status is ToolStatus.OK and not self.success:
            raise ValueError("OK ToolResult must be successful")
        if self.status in {ToolStatus.TIMEOUT, ToolStatus.FAILED} and self.success:
            raise ValueError("TIMEOUT and FAILED ToolResult cannot be successful")
        if self.success and self.error is not None:
            raise ValueError("successful ToolResult cannot contain an error")
        if not self.success and self.error is None:
            raise ValueError("unsuccessful ToolResult requires an error")
        return self


def normalize_legacy_tool_result(value: dict[str, Any]) -> ToolResult:
    """Normalize the immutable-design legacy wire shape at a read boundary."""

    legacy = dict(value)
    status = legacy.get("status")
    if status == "SUCCESS":
        legacy["status"] = ToolStatus.OK

    meta_value = dict(legacy.get("meta") or {})
    if "trace_id" in legacy and "trace_id" not in meta_value:
        meta_value["trace_id"] = legacy.pop("trace_id")
    if "source_system" not in meta_value:
        meta_value["source_system"] = legacy.pop("source_system", "unknown")
    if "provider_type" not in meta_value:
        meta_value["provider_type"] = legacy.pop("source", "real")
    meta_value.setdefault("partial_result", False)
    meta_value.setdefault("latency_ms", 0)
    meta_value.setdefault("attempts", 1)
    meta_value.setdefault("retryable", False)
    meta_value.setdefault("retry_after_seconds", None)
    legacy["meta"] = meta_value

    error_code = legacy.pop("error_code", "")
    error_message = legacy.pop("error_message", "")
    if legacy.get("error") is None and not legacy.get("success", False):
        legacy["error"] = {
            "code": error_code or "TOOL_FAILED",
            "message": error_message or "tool call failed",
            "details": {},
        }
    legacy.setdefault("warnings", [])
    return ToolResult.model_validate(legacy)
