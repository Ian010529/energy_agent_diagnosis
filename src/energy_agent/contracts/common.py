"""Shared enums and strict boundary-model primitives."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer


class StrictModel(BaseModel):
    """Base for every cross-boundary object."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _utc_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise TypeError("value must be an ISO8601 datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return value.astimezone(UTC)


def _format_utc_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


UTCDateTime = Annotated[
    datetime,
    BeforeValidator(_utc_datetime),
    PlainSerializer(_format_utc_datetime, return_type=str),
]


class RunStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    NEED_USER_INPUT = "NEED_USER_INPUT"
    FAILED = "FAILED"


class DiagnosisPhase(StrEnum):
    INIT = "INIT"
    PLAN_READY = "PLAN_READY"
    DATA_FETCHING = "DATA_FETCHING"
    EVIDENCE_READY = "EVIDENCE_READY"
    NEED_USER_INPUT = "NEED_USER_INPUT"
    DRAFT_READY = "DRAFT_READY"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AlarmDiagnosisStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DISPATCHED = "DISPATCHED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    FAILED = "FAILED"


class ToolStatus(StrEnum):
    OK = "OK"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    NOT_FOUND = "NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class ApprovalState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class CaseStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISABLED = "DISABLED"
    SUPERSEDED = "SUPERSEDED"


class IndexState(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    INDEXED = "INDEXED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    TOMBSTONED = "TOMBSTONED"
