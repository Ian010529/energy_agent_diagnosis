from enum import StrEnum
from typing import Any, Literal

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
    class ManualSearchFilters(StrictModel):
        device_type: str | None = None
        device_model: str | None = None
        manufacturer: str | None = None
        alarm_name: str | None = None
        doc_version: str | None = None
        section_type: list[Literal["正文", "表格", "告警定义", "维护步骤", "注意事项"]] = Field(
            default_factory=list
        )
        effective_only: bool = True

    context: ToolContext
    query: str
    filters: ManualSearchFilters = Field(default_factory=ManualSearchFilters)
    retrieval_mode: Literal["hybrid", "keyword_only", "vector_only"] = "hybrid"
    score_threshold: float = Field(default=0.45, ge=0, le=1)
    top_k: int = Field(default=5, ge=1, le=20)


class TicketSearchInput(StrictModel):
    class TicketSearchFilters(StrictModel):
        device_type: str | None = None
        device_model: str | None = None
        manufacturer: str | None = None
        alarm_name: str | None = None
        site_id: str | None = None
        exclude_ticket_ids: list[str] = Field(default_factory=list)

    context: ToolContext
    query: str
    filters: TicketSearchFilters = Field(default_factory=TicketSearchFilters)
    retrieval_mode: Literal["hybrid", "keyword_only", "vector_only"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=20)
    verified_only: bool = True
    time_range_months: int = Field(default=12, ge=1)
    score_threshold: float = Field(default=0.50, ge=0, le=1)


ManualSearchFilters = ManualSearchInput.ManualSearchFilters
TicketSearchFilters = TicketSearchInput.TicketSearchFilters
