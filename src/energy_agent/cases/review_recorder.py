from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from energy_agent.tools.contracts import AppendCaseReviewInput


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    review_id: str
    created_at: datetime


class DiagnosisReviewRecorder(Protocol):
    async def append(self, request: AppendCaseReviewInput) -> ReviewRecord: ...
