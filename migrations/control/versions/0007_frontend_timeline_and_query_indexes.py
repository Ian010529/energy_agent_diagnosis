"""Phase 7 frontend timeline and read-query indexes.

Revision ID: 0007_phase7
Revises: 0006_phase6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0007_phase7"
down_revision: str | Sequence[str] | None = "0006_phase6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _indexes(table: str) -> set[str]:
    return {str(index["name"]) for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _add_index(name: str, table: str, columns: list[str]) -> None:
    if name not in _indexes(table):
        op.create_index(name, table, columns)


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("diagnosis_timeline_event"):
        op.create_table(
            "diagnosis_timeline_event",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("event_id", sa.String(64), nullable=False),
            sa.Column(
                "session_id",
                sa.String(64),
                sa.ForeignKey("diagnosis_session.id"),
                nullable=False,
            ),
            sa.Column("run_id", sa.String(64)),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(64), nullable=False),
            sa.Column("actor_id", sa.String(128)),
            sa.Column("actor_role", sa.String(32)),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
            sa.UniqueConstraint("event_id", name="uq_timeline_event_id"),
            sa.UniqueConstraint("session_id", "sequence", name="uq_timeline_session_sequence"),
        )
        op.create_index(
            "ix_timeline_session_sequence",
            "diagnosis_timeline_event",
            ["session_id", "sequence"],
        )
        op.create_index("ix_timeline_run_id", "diagnosis_timeline_event", ["run_id"])
        op.create_index("ix_timeline_created_at", "diagnosis_timeline_event", ["created_at"])
    _add_index("ix_session_updated_id", "diagnosis_session", ["updated_at", "id"])
    _add_index("ix_session_phase_updated", "diagnosis_session", ["phase", "updated_at"])
    _add_index("ix_session_creator_updated", "diagnosis_session", ["created_by", "updated_at"])
    _add_index(
        "ix_device_site_type_id",
        "device_profile",
        ["site_id", "device_type", "device_id"],
    )
    _add_index("ix_device_status_id", "device_profile", ["status", "device_id"])
    _add_index("ix_alarm_site_time_id", "alarm_event", ["site_id", "trigger_time", "alarm_id"])
    _add_index(
        "ix_alarm_device_time_id",
        "alarm_event",
        ["device_id", "trigger_time", "alarm_id"],
    )
    _add_index(
        "ix_alarm_status_time_id",
        "alarm_event",
        ["status", "trigger_time", "alarm_id"],
    )
    _add_index(
        "ix_case_review_updated_id",
        "diagnosis_case",
        ["review_status", "updated_at", "case_id"],
    )


def downgrade() -> None:
    for name, table in (
        ("ix_case_review_updated_id", "diagnosis_case"),
        ("ix_alarm_status_time_id", "alarm_event"),
        ("ix_alarm_device_time_id", "alarm_event"),
        ("ix_alarm_site_time_id", "alarm_event"),
        ("ix_device_status_id", "device_profile"),
        ("ix_device_site_type_id", "device_profile"),
        ("ix_session_creator_updated", "diagnosis_session"),
        ("ix_session_phase_updated", "diagnosis_session"),
        ("ix_session_updated_id", "diagnosis_session"),
    ):
        if name in _indexes(table):
            op.drop_index(name, table_name=table)
    op.drop_table("diagnosis_timeline_event")
