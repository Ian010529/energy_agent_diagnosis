"""Phase 4 human collaboration and reviewed case lifecycle.

Revision ID: 0004_phase4
Revises: 0003_phase3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0004_phase4"
down_revision: str | Sequence[str] | None = "0003_phase3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("diagnosis_session", sa.Column("created_by", sa.String(128)))
    op.add_column("diagnosis_session", sa.Column("latest_review_status", sa.String(32)))
    op.add_column("diagnosis_run", sa.Column("parent_run_id", sa.String(64)))
    op.add_column(
        "diagnosis_run",
        sa.Column("run_type", sa.String(32), nullable=False, server_default="diagnosis"),
    )
    op.create_table(
        "diagnosis_review",
        sa.Column("review_id", sa.String(64), primary_key=True),
        sa.Column(
            "session_id", sa.String(64), sa.ForeignKey("diagnosis_session.id"), nullable=False
        ),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("review_result", sa.String(32), nullable=False),
        sa.Column("root_cause", sa.Text()),
        sa.Column("resolution_steps", sa.JSON(), nullable=False),
        sa.Column("comments", sa.Text()),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("source_ticket_id", sa.String(128)),
        sa.Column("override_reason", sa.Text()),
        sa.Column("requested_questions", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_review_session_idempotency"),
    )
    op.create_index("ix_diagnosis_review_session_id", "diagnosis_review", ["session_id"])
    op.create_table(
        "diagnosis_case",
        sa.Column("case_id", sa.String(64), primary_key=True),
        sa.Column("source_session_id", sa.String(64), nullable=False),
        sa.Column("source_run_id", sa.String(64), nullable=False),
        sa.Column("source_review_id", sa.String(64), nullable=False),
        sa.Column("source_ticket_id", sa.String(128)),
        sa.Column("device_type", sa.String(64)),
        sa.Column("device_model", sa.String(128)),
        sa.Column("manufacturer", sa.String(128)),
        sa.Column("alarm_name", sa.String(255)),
        sa.Column("symptom_summary", sa.Text()),
        sa.Column("timeseries_features", sa.Text()),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("resolution_steps", sa.JSON(), nullable=False),
        sa.Column("safety_notes", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("reviewer", sa.String(128)),
        sa.Column("review_comment", sa.Text()),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("embedding_text", sa.Text()),
        sa.Column("index_status", sa.String(32), nullable=False),
        sa.Column("index_error_code", sa.String(64)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("supersedes_case_id", sa.String(64)),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "review_status IN "
            "('DRAFT','PENDING_REVIEW','APPROVED','REJECTED','DISABLED','SUPERSEDED')",
            name="ck_case_review_status",
        ),
        sa.CheckConstraint("case_version >= 1", name="ck_case_version"),
        sa.UniqueConstraint("source_session_id", "case_version", name="uq_case_session_version"),
    )
    op.create_index("ix_case_source_session", "diagnosis_case", ["source_session_id"])
    op.create_index(
        "ix_case_retrieval",
        "diagnosis_case",
        ["review_status", "index_status", "is_active"],
    )
    op.create_table(
        "case_review_event",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32)),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint("case_id", "idempotency_key", name="uq_case_event_idempotency"),
    )
    op.create_index("ix_case_review_event_case_id", "case_review_event", ["case_id"])
    op.create_table(
        "audit_event",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.String(128), nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(64)),
        sa.Column("case_id", sa.String(64)),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("safe_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
    )
    op.create_index("ix_audit_event_actor_id", "audit_event", ["actor_id"])
    op.create_index("ix_audit_event_action", "audit_event", ["action"])


def downgrade() -> None:
    op.drop_table("audit_event")
    op.drop_table("case_review_event")
    op.drop_table("diagnosis_case")
    op.drop_table("diagnosis_review")
    op.drop_column("diagnosis_run", "run_type")
    op.drop_column("diagnosis_run", "parent_run_id")
    op.drop_column("diagnosis_session", "latest_review_status")
    op.drop_column("diagnosis_session", "created_by")
