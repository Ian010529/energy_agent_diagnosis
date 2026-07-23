from dataclasses import dataclass
from enum import StrEnum

from energy_agent.contracts.common import StrictModel


@dataclass(frozen=True, slots=True)
class AlarmDedupHit:
    session_id: str
    hit_count: int


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class BreakerSnapshot(StrictModel):
    dependency: str
    state: CircuitState
    failure_count: int
    opened_at: float | None = None
    single_process: bool = True
