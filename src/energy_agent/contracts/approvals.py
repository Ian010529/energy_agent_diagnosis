"""Approval request and decision DTOs; no approval behavior is implemented in M1."""

from __future__ import annotations

from pydantic import Field

from energy_agent.contracts.common import ApprovalState, StrictModel, UTCDateTime, UUIDv7String


class ApprovalRequest(StrictModel):
    approval_id: UUIDv7String
    tenant_id: str
    target_type: str
    target_id: str
    action: str
    requester_id: str
    state: ApprovalState = ApprovalState.PENDING
    revision: int = Field(default=1, ge=1)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonicalization_version: int = Field(default=2, ge=2, le=2)
    created_at: UTCDateTime


class ApprovalDecision(StrictModel):
    approval_id: UUIDv7String
    expected_revision: int = Field(ge=1)
    decision: ApprovalState
    decision_actor_id: str
    decision_actor_role: str
    decision_reason: str
    emergency: bool = False
    decided_at: UTCDateTime
    trace_id: UUIDv7String
