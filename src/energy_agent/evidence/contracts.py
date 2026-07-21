from datetime import datetime
from typing import Literal

from pydantic import Field

from energy_agent.contracts.common import StrictModel


class EvidenceDetail(StrictModel):
    evidence_id: str
    source_type: str
    source_id: str
    title: str
    summary: str
    citation: str
    verified: bool
    scores: dict[str, float | None]
    metadata: dict[str, object] = Field(default_factory=dict)
    content_excerpt: str | None = None
    manual_location: dict[str, object] | None = None
    ticket_detail: dict[str, object] | None = None
    case_detail: dict[str, object] | None = None
    timeseries_descriptor: dict[str, object] | None = None


class TimeseriesPoint(StrictModel):
    timestamp: datetime
    value: float
    quality: str = "good"


class TimeseriesSeries(StrictModel):
    metric: str
    unit: str | None = None
    points: list[TimeseriesPoint]


class SessionTimeseriesResponse(StrictModel):
    device_id: str
    start_time: datetime
    end_time: datetime
    window_source: Literal["requested", "session_memory", "alarm", "current"]
    empty_reason: str | None = None
    series: list[TimeseriesSeries]
