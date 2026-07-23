from datetime import datetime

from pydantic import Field

from energy_agent.contracts.common import StrictModel


class DatasetCapability(StrictModel):
    id: str
    version: str


class AuthCapability(StrictModel):
    mode: str
    pilot_mode: bool


class TemplateCapability(StrictModel):
    template_id: str
    template_version: str
    device_type: str
    alarm_category: str
    alarm_patterns: list[str]
    measurements: list[str]
    metrics: list[str]


class CapabilitiesResponse(StrictModel):
    api_version: str = "v1"
    app_version: str
    active_dataset: DatasetCapability
    auth: AuthCapability
    templates: list[TemplateCapability]
    device_types: list[str]
    features: dict[str, bool]
    limits: dict[str, int]


class SiteItem(StrictModel):
    site_id: str
    display_name: str
    device_count: int
    active_alarm_count: int
    device_type_counts: dict[str, int]
    status_counts: dict[str, int]


class SiteListResponse(StrictModel):
    items: list[SiteItem]


class DeviceItem(StrictModel):
    device_id: str
    site_id: str
    device_type: str
    device_model: str
    manufacturer: str
    commission_time: datetime | None = None
    location: str | None = None
    status: str
    rated_power: float | None = None
    latest_alarm_count: int = 0


class DeviceListResponse(StrictModel):
    items: list[DeviceItem]
    next_cursor: str | None = None
    has_more: bool = False


class AlarmItem(StrictModel):
    alarm_id: str
    device_id: str
    site_id: str
    alarm_name: str
    alarm_level: str
    trigger_time: datetime
    status: str
    source_system: str
    alarm_category: str | None = None
    supported: bool
    template_id: str | None = None
    template_version: str | None = None


class AlarmRecord(StrictModel):
    alarm_id: str
    device_id: str
    site_id: str
    device_type: str
    alarm_name: str
    alarm_level: str
    trigger_time: datetime
    status: str
    source_system: str


class AlarmListResponse(StrictModel):
    items: list[AlarmItem]
    next_cursor: str | None = None
    has_more: bool = False


class DiagnosisSessionItem(StrictModel):
    session_id: str
    run_id: str
    source: str
    site_id: str | None = None
    device_id: str | None = None
    alarm_id: str | None = None
    alarm_name: str | None = None
    phase: str
    risk_level: str
    trace_id: str
    created_by: str | None = None
    latest_review_status: str | None = None
    final_summary: str | None = None
    diagnosis_template_id: str | None = None
    diagnosis_template_version: str | None = None
    alarm_category: str | None = None
    guardrail_status: str | None = None
    failure_category: str | None = None
    created_at: datetime
    updated_at: datetime


class DiagnosisSessionListResponse(StrictModel):
    items: list[DiagnosisSessionItem]
    next_cursor: str | None = None
    has_more: bool = False


class CatalogPage(StrictModel):
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = None
