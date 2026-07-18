"""Phase 1 control-plane tables.

Revision ID: 0001_phase1
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001_phase1"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_session",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("site_id", sa.String(128)),
        sa.Column("device_id", sa.String(128)),
        sa.Column("alarm_id", sa.String(128)),
        sa.Column("alarm_name", sa.String(255)),
        sa.Column("phase", sa.String(32), nullable=False),
        sa.Column("final_summary", sa.Text()),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "phase IN ('INIT','PLAN_READY','DATA_FETCHING','EVIDENCE_READY',"
            "'NEED_USER_INPUT','DRAFT_READY','REVIEWING','COMPLETED','FAILED')",
            name="ck_diagnosis_session_phase",
        ),
    )
    op.create_table(
        "diagnosis_step_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("diagnosis_session.id"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("step_name", sa.String(128), nullable=False),
        sa.Column("step_status", sa.String(32), nullable=False),
        sa.Column("input_snapshot", sa.JSON()),
        sa.Column("output_snapshot", sa.JSON()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("ended_at", mysql.DATETIME(fsp=6)),
        sa.Column("duration_ms", sa.Integer()),
    )
    op.create_index(
        "ix_step_log_session_id",
        "diagnosis_step_log",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_table("diagnosis_step_log")
    op.drop_table("diagnosis_session")
