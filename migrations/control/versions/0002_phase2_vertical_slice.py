"""Phase 2 diagnosis vertical slice tables.

Revision ID: 0002_phase2
Revises: 0001_phase1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002_phase2"
down_revision: str | Sequence[str] | None = "0001_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_run",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "session_id", sa.String(64), sa.ForeignKey("diagnosis_session.id"), nullable=False
        ),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("ended_at", mysql.DATETIME(fsp=6)),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_run_session_idempotency"),
    )
    op.create_index("ix_diagnosis_run_session_id", "diagnosis_run", ["session_id"])
    op.create_table(
        "diagnosis_result",
        sa.Column("run_id", sa.String(64), sa.ForeignKey("diagnosis_run.id"), primary_key=True),
        sa.Column(
            "session_id", sa.String(64), sa.ForeignKey("diagnosis_session.id"), nullable=False
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("candidate_causes", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("inspection_steps", sa.JSON(), nullable=False),
        sa.Column("safety_notes", sa.JSON(), nullable=False),
        sa.Column("missing_information", sa.JSON(), nullable=False),
        sa.Column("recommend_ticket", sa.Boolean(), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("degraded_components", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
    )
    op.create_index("ix_diagnosis_result_session_id", "diagnosis_result", ["session_id"])
    op.create_table(
        "device_profile",
        sa.Column("device_id", sa.String(128), primary_key=True),
        sa.Column("site_id", sa.String(128), nullable=False),
        sa.Column("device_type", sa.String(64), nullable=False),
        sa.Column("device_model", sa.String(128), nullable=False),
        sa.Column("manufacturer", sa.String(128), nullable=False),
        sa.Column("commission_time", mysql.DATETIME(fsp=6)),
        sa.Column("location", sa.String(255)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("rated_power", sa.Float()),
    )
    op.create_index("ix_device_profile_site_id", "device_profile", ["site_id"])
    op.create_table(
        "alarm_event",
        sa.Column("alarm_id", sa.String(128), primary_key=True),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("site_id", sa.String(128), nullable=False),
        sa.Column("alarm_name", sa.String(255), nullable=False),
        sa.Column("alarm_level", sa.String(32), nullable=False),
        sa.Column("trigger_time", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
    )
    op.create_index("ix_alarm_event_device_id", "alarm_event", ["device_id"])
    op.create_table(
        "manual_chunk",
        sa.Column("chunk_id", sa.String(128), primary_key=True),
        sa.Column("doc_id", sa.String(128), nullable=False),
        sa.Column("device_type", sa.String(64), nullable=False),
        sa.Column("device_model", sa.String(128)),
        sa.Column("manufacturer", sa.String(128)),
        sa.Column("alarm_name", sa.String(255)),
        sa.Column("chapter_title", sa.String(255), nullable=False),
        sa.Column("page_no", sa.Integer()),
        sa.Column("section_type", sa.String(64), nullable=False),
        sa.Column("summary_or_content", sa.Text(), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("effective", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_manual_chunk_doc_id", "manual_chunk", ["doc_id"])
    op.create_table(
        "maintenance_ticket",
        sa.Column("ticket_id", sa.String(128), primary_key=True),
        sa.Column("site_id", sa.String(128), nullable=False),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("device_model", sa.String(128), nullable=False),
        sa.Column("alarm_name", sa.String(255), nullable=False),
        sa.Column("fault_symptom", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("action_taken", sa.Text(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("close_time", mysql.DATETIME(fsp=6)),
    )
    op.create_index("ix_maintenance_ticket_is_verified", "maintenance_ticket", ["is_verified"])


def downgrade() -> None:
    for table in (
        "maintenance_ticket",
        "manual_chunk",
        "alarm_event",
        "device_profile",
        "diagnosis_result",
        "diagnosis_run",
    ):
        op.drop_table(table)
