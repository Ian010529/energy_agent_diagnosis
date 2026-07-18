from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from energy_agent.contracts.common import StrictModel


class ToolStatus(StrEnum):
    OK = "OK"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class ToolContext(StrictModel):
    tenant_id: str | None = None
    org_id: str | None = None
    site_id: str | None = None
    trace_id: str
    operator_id: str | None = None
    source_system: str


class ToolMeta(StrictModel):
    trace_id: str
    source_system: str
    provider_type: str = "real"
    partial_result: bool = False
    latency_ms: int = 0
    attempts: int = 1
    retryable: bool = False
    retrieval_mode: str | None = None


class ToolResult(StrictModel):
    success: bool
    status: ToolStatus
    data: Any = None
    meta: ToolMeta
    error_code: str = ""
    error_message: str = ""
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_success(cls, value: object) -> object:
        if isinstance(value, dict) and value.get("status") == "SUCCESS":
            return {**value, "status": "OK"}
        return value

    @model_validator(mode="after")
    def require_failure_code(self) -> "ToolResult":
        if not self.success and not self.error_code:
            raise ValueError("failed ToolResult requires error_code")
        return self


class DeviceProfileInput(StrictModel):
    context: ToolContext
    device_id: str
    include_fields: list[str] = Field(default_factory=list)


class AlarmDetailInput(StrictModel):
    context: ToolContext
    alarm_id: str
    device_id: str | None = None
    include_raw_payload: bool = False


class TimeseriesWindowInput(StrictModel):
    context: ToolContext
    device_id: str
    metrics: list[str] = Field(min_length=1)
    start_time: str
    end_time: str
    aggregation: str = "trend"
    granularity: str = "5m"
    max_points: int = Field(default=500, ge=1, le=5000)


class ManualSearchInput(StrictModel):
    context: ToolContext
    query: str
    filters: dict[str, object] = Field(default_factory=dict)
    retrieval_mode: str = "keyword_only"
    score_threshold: float = Field(default=0.0, ge=0, le=1)
    top_k: int = Field(default=5, ge=1, le=20)


class TicketSearchInput(StrictModel):
    context: ToolContext
    query: str
    filters: dict[str, object] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=20)
    verified_only: bool = True
    time_range_months: int = Field(default=12, ge=1)
    score_threshold: float = Field(default=0.0, ge=0, le=1)
