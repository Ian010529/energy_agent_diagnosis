"""Phase 6 pilot hardening fields and alarm deduplication.

Revision ID: 0006_phase6
Revises: 0005_phase5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0006_phase6"
down_revision: str | Sequence[str] | None = "0005_phase5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str) -> set[str]:
    return {str(column["name"]) for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    run_columns = _columns("diagnosis_run")
    if "first_event_at" not in run_columns:
        op.add_column("diagnosis_run", sa.Column("first_event_at", mysql.DATETIME(fsp=6)))
    if "guardrail_status" not in run_columns:
        op.add_column("diagnosis_run", sa.Column("guardrail_status", sa.String(32)))
    if "failure_category" not in run_columns:
        op.add_column("diagnosis_run", sa.Column("failure_category", sa.String(64)))
    result_columns = _columns("diagnosis_result")
    if "recommended_actions" not in result_columns:
        op.add_column(
            "diagnosis_result",
            sa.Column("recommended_actions", sa.JSON(), nullable=True),
        )
        op.execute(
            sa.text(
                "UPDATE diagnosis_result SET recommended_actions = JSON_ARRAY() "
                "WHERE recommended_actions IS NULL"
            )
        )
        op.alter_column(
            "diagnosis_result",
            "recommended_actions",
            existing_type=sa.JSON(),
            nullable=False,
        )
    if "guardrail_decision" not in result_columns:
        op.add_column("diagnosis_result", sa.Column("guardrail_decision", sa.JSON()))
    if not sa.inspect(op.get_bind()).has_table("diagnosis_alarm_dedup"):
        op.create_table(
            "diagnosis_alarm_dedup",
            sa.Column("dedup_key", sa.String(64), primary_key=True),
            sa.Column("device_id", sa.String(128), nullable=False),
            sa.Column("alarm_category", sa.String(128), nullable=False),
            sa.Column(
                "session_id",
                sa.String(64),
                sa.ForeignKey("diagnosis_session.id"),
                nullable=False,
            ),
            sa.Column("alarm_ids", sa.JSON(), nullable=False),
            sa.Column("first_seen_at", mysql.DATETIME(fsp=6), nullable=False),
            sa.Column("last_seen_at", mysql.DATETIME(fsp=6), nullable=False),
            sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
            sa.Column("hit_count", sa.Integer(), nullable=False),
            sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
            sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        )
        op.create_index(
            "ix_alarm_dedup_lookup",
            "diagnosis_alarm_dedup",
            ["device_id", "alarm_category", "expires_at"],
        )


def downgrade() -> None:
    op.drop_table("diagnosis_alarm_dedup")
    op.drop_column("diagnosis_result", "guardrail_decision")
    op.drop_column("diagnosis_result", "recommended_actions")
    op.drop_column("diagnosis_run", "failure_category")
    op.drop_column("diagnosis_run", "guardrail_status")
    op.drop_column("diagnosis_run", "first_event_at")
