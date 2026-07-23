from enum import StrEnum
from typing import Protocol

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


class GraphPort(Protocol):
    async def project_template(self, payload: dict[str, object]) -> None: ...

    async def project_case(
        self,
        *,
        case_id: str,
        case_version: int,
        device_type: str,
        alarm_name: str,
        fault_cause: str,
        resolution_action: str,
    ) -> None: ...

    async def tombstone_case(self, case_id: str) -> None: ...

    async def query_relations(
        self,
        *,
        alarm_name: str,
        device_type: str | None,
        component: str | None,
        relation_depth: int,
        top_k: int,
    ) -> list[GraphRelation]: ...
