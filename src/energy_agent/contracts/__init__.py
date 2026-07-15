"""Single public import surface for M1 shared contracts."""

from energy_agent.contracts.approvals import ApprovalDecision, ApprovalRequest
from energy_agent.contracts.cases import CaseRecord
from energy_agent.contracts.common import (
    AlarmDiagnosisStatus,
    ApprovalState,
    CaseStatus,
    DiagnosisPhase,
    IndexState,
    RunStatus,
    ToolStatus,
    UUIDv7String,
)
from energy_agent.contracts.diagnosis import RunAcceptedResponse
from energy_agent.contracts.errors import ErrorDetail, ErrorEnvelope
from energy_agent.contracts.events import EventEnvelope, PublicSSEEvent, PublicSSEEventType
from energy_agent.contracts.index import IndexEvent
from energy_agent.contracts.migrations import MigrationResult, MigrationStatus, SchemaManifest
from energy_agent.contracts.model import ModelAttempt, ModelAttemptStatus
from energy_agent.contracts.tools import (
    ToolError,
    ToolMeta,
    ToolResult,
    normalize_legacy_tool_result,
)

__all__ = [
    "AlarmDiagnosisStatus",
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalState",
    "CaseRecord",
    "CaseStatus",
    "DiagnosisPhase",
    "ErrorDetail",
    "ErrorEnvelope",
    "EventEnvelope",
    "IndexEvent",
    "IndexState",
    "MigrationResult",
    "MigrationStatus",
    "ModelAttempt",
    "ModelAttemptStatus",
    "PublicSSEEvent",
    "PublicSSEEventType",
    "RunAcceptedResponse",
    "RunStatus",
    "SchemaManifest",
    "ToolError",
    "ToolMeta",
    "ToolResult",
    "ToolStatus",
    "UUIDv7String",
    "normalize_legacy_tool_result",
]
