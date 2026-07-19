from enum import StrEnum

from pydantic import Field

from energy_agent.contracts.common import StrictModel


class GraphProjectionStatus(StrEnum):
    PENDING = "PENDING"
    PROJECTED = "PROJECTED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    TOMBSTONED = "TOMBSTONED"


class GraphRelation(StrictModel):
    alarm_name: str
    fault_cause: str
    component: str | None = None
    actions: list[str] = Field(default_factory=list)
    support_case_ids: list[str] = Field(default_factory=list)
    support_count: int = Field(default=0, ge=0)
    template_ids: list[str] = Field(default_factory=list)
