"""定义入口、工具、证据、诊断和认证共享的数据契约。"""

from enum import StrEnum
from typing import Any

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Role(StrEnum):
    """系统支持的最小角色集合。"""

    VIEWER = "viewer"
    OPERATOR = "operator"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class Principal(BaseModel):
    """表示通过认证后可供路由和业务模块消费的用户身份。"""

    user_id: str
    roles: frozenset[Role]


class ProviderType(StrEnum):
    """标识数据来自 Mock 还是真实 Provider。"""

    MOCK = "mock"
    REAL = "real"


class ToolStatus(StrEnum):
    """工具调用在各文档中约定的完整状态集合。"""

    OK = "OK"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class DiagnosisStatus(StrEnum):
    """诊断状态机的公共状态；阶段 1 只定义契约，不执行状态机。"""

    INIT = "INIT"
    PLAN_READY = "PLAN_READY"
    DATA_FETCHING = "DATA_FETCHING"
    EVIDENCE_READY = "EVIDENCE_READY"
    NEED_USER_INPUT = "NEED_USER_INPUT"
    DRAFT_READY = "DRAFT_READY"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AlarmContext(BaseModel):
    """保存告警标识和时间，并兼容历史字段 ``alarm_time``。"""

    alarm_id: str | None = None
    alarm_name: str | None = None
    alarm_level: str | None = None
    trigger_time: AwareDatetime | None = Field(
        default=None,
        validation_alias=AliasChoices("trigger_time", "alarm_time"),
    )


class TimeWindow(BaseModel):
    """表示工具查询时间窗，并兼容短字段名。"""

    start_time: AwareDatetime = Field(validation_alias=AliasChoices("start_time", "start"))
    end_time: AwareDatetime = Field(validation_alias=AliasChoices("end_time", "end"))


class RequestContext(BaseModel):
    """统一告警入口和对话入口进入 Agent 前的请求上下文。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    request_id: str
    trace_id: str
    session_id: str
    request_source: str = Field(validation_alias=AliasChoices("request_source", "source"))
    user_id: str | None = None
    role: Role | None = None
    site_id: str | None = None
    device_id: str | None = None
    device_type: str | None = None
    device_model: str | None = None
    manufacturer: str | None = None
    alarm: AlarmContext | None = None
    message: str | None = None
    stream: bool = True
    debug: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_nested_shape(cls, value: Any) -> Any:
        """显式展开文档标准嵌套结构，禁止未知字段被静默丢弃。"""
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        mappings = {
            "user": {"user_id": "user_id", "role": "role"},
            "site": {"site_id": "site_id"},
            "device": {
                "device_id": "device_id",
                "device_type": "device_type",
                "device_model": "device_model",
                "manufacturer": "manufacturer",
            },
            "options": {"stream": "stream", "debug": "debug"},
        }
        for group, fields in mappings.items():
            nested = payload.pop(group, None)
            if nested is None:
                continue
            if not isinstance(nested, dict):
                raise ValueError(f"{group} 必须是对象")
            unknown = set(nested).difference(fields)
            if unknown:
                raise ValueError(f"{group} 包含未知字段: {sorted(unknown)}")
            for external, internal in fields.items():
                if external in nested and internal not in payload:
                    payload[internal] = nested[external]
        return payload


class ToolContext(BaseModel):
    """工具调用必须透传的租户、站点、操作者和追踪信息。"""

    trace_id: str
    source_system: str
    tenant_id: str | None = None
    org_id: str | None = None
    site_id: str | None = None
    operator_id: str | None = None


class ToolMeta(BaseModel):
    """保存工具响应的来源、耗时和降级元数据。"""

    trace_id: str = Field(min_length=1)
    source_system: str | None = None
    provider_type: ProviderType | None = None
    partial_result: bool = False
    latency_ms: int | None = Field(default=None, ge=0)


class ToolResult[T](BaseModel):
    """工具的内部超集返回结构，并在边界归一化旧字段。"""

    model_config = ConfigDict(extra="forbid")

    success: bool
    status: ToolStatus
    data: T | None = None
    meta: ToolMeta
    error_code: str = ""
    error_message: str = ""
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_compatible_shape(cls, value: Any) -> Any:
        """把文档中的紧凑和企业级结构归一化为同一模型。"""
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        # SUCCESS 是既有详细设计中的成功值；内部只保留 OK，避免分支扩散。
        if str(payload.get("status", "")).upper() == "SUCCESS":
            payload["status"] = ToolStatus.OK

        raw_meta = payload.get("meta")
        if isinstance(raw_meta, ToolMeta):
            # Pydantic 在直接构造模型时会先传入已验证子模型，不能把它误当成空值覆盖。
            meta = raw_meta.model_dump()
        else:
            meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        for field_name in (
            "trace_id",
            "source_system",
            "provider_type",
            "partial_result",
            "latency_ms",
        ):
            top_value = payload.pop(field_name, None)
            if top_value is not None and field_name not in meta:
                meta[field_name] = top_value

        source = payload.pop("source", None)
        if source in {ProviderType.MOCK, ProviderType.REAL, "mock", "real"}:
            meta.setdefault("provider_type", source)
        elif source:
            meta.setdefault("source_system", source)
        payload["meta"] = meta
        return payload

    @model_validator(mode="after")
    def validate_error(self) -> "ToolResult[T]":
        """确保成功标记、状态和错误码保持一致。"""
        successful_statuses = {ToolStatus.OK, ToolStatus.PARTIAL_SUCCESS}
        if self.success != (self.status in successful_statuses):
            raise ValueError("ToolResult 的 success 与 status 不一致")
        if not self.success and not self.error_code:
            raise ValueError("失败的 ToolResult 必须包含 error_code")
        return self


class EvidenceItem(BaseModel):
    """表示一次诊断可引用的单条证据。"""

    evidence_id: str
    source_type: str
    source_id: str
    chunk_id: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    section: str | None = None
    time_window: TimeWindow | None = None
    quote_text: str
    score: float = Field(ge=0, le=1)
    verified: bool = False
    weak_evidence: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidencePackage(BaseModel):
    """在检索、工具和生成模块之间传递有序证据。"""

    package_id: str
    session_id: str
    trace_id: str
    ranked_evidence: list[EvidenceItem] = Field(default_factory=list)
    degraded_sources: list[str] = Field(default_factory=list)
    need_manual_confirmation: bool = False


class CandidateCause(BaseModel):
    """表示一个带支持证据和不确定性的候选根因。"""

    cause: str
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    need_manual_confirmation: bool = False


class TicketSuggestion(BaseModel):
    """表示需要权限和人工确认门禁的工单草稿或提交建议。"""

    action: str
    summary: str
    draft: bool = True
    requires_confirmation: bool = True
    submitted: bool = False
    ticket_id: str | None = None


class DiagnosisResult(BaseModel):
    """API、持久化和前端共同消费的标准诊断结果。"""

    session_id: str
    status: DiagnosisStatus
    summary: str = ""
    candidate_causes: list[CandidateCause] = Field(default_factory=list)
    investigation_steps: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    ticket_suggestion: TicketSuggestion | None = None
    evidence_package_id: str | None = None
    generated_at: AwareDatetime | None = None


class ErrorResponse(BaseModel):
    """所有 HTTP 异常使用的稳定错误响应。"""

    error_code: str
    error_message: str
    trace_id: str
    details: dict[str, Any] | None = None
