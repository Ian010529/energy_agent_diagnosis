from dataclasses import dataclass
from typing import Protocol

from energy_agent.catalog.contracts import AlarmRecord
from energy_agent.contracts.diagnosis import (
    DiagnosisResultRecord,
    DiagnosisRunRecord,
    DiagnosisSessionRecord,
    SessionMemoryPayload,
)


@dataclass(frozen=True, slots=True)
class EvidenceSourceDetail:
    title: str
    payload_name: str
    payload: dict[str, object]
    content_excerpt: str | None = None


class EvidenceSourcePort(Protocol):
    async def manual(self, source_id: str) -> EvidenceSourceDetail | None: ...

    async def ticket(self, source_id: str) -> EvidenceSourceDetail | None: ...

    async def case(self, source_id: str) -> EvidenceSourceDetail | None: ...


class EvidenceSessionPort(Protocol):
    async def get(self, session_id: str, *, trace_id: str) -> DiagnosisSessionRecord | None: ...


class EvidenceResultPort(Protocol):
    async def latest(self, session_id: str) -> DiagnosisResultRecord | None: ...


class EvidenceRunPort(Protocol):
    async def get_for_session(
        self, run_id: str, session_id: str, *, trace_id: str
    ) -> DiagnosisRunRecord | None: ...

    async def latest(self, session_id: str, *, trace_id: str) -> DiagnosisRunRecord | None: ...


class EvidenceMemoryPort(Protocol):
    async def get(self, session_id: str, *, trace_id: str) -> SessionMemoryPayload | None: ...


class EvidenceCatalogPort(Protocol):
    async def alarm(self, alarm_id: str) -> AlarmRecord: ...
