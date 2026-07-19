"""Phase 5 asynchronous indexing, graph projections and scenario templates.

Revision ID: 0005_phase5
Revises: 0004_phase4
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0005_phase5"
down_revision: str | Sequence[str] | None = "0004_phase4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("maintenance_ticket", sa.Column("index_generation", sa.String(64)))
    op.create_table(
        "index_job",
        sa.Column("job_id", sa.String(64), primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("entity_version", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("causation_id", sa.String(64), nullable=False),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("last_error_message", sa.String(512)),
        sa.Column("next_attempt_at", mysql.DATETIME(fsp=6)),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6)),
        sa.Column("finished_at", mysql.DATETIME(fsp=6)),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "entity_version",
            "operation",
            name="uq_index_job_entity_operation",
        ),
    )
    op.create_index("ix_index_job_status_next_attempt", "index_job", ["status", "next_attempt_at"])
    op.create_table(
        "index_outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("index_job.job_id"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("publish_status", sa.String(32), nullable=False),
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("published_at", mysql.DATETIME(fsp=6)),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
    )
    op.create_index("ix_index_outbox_job_id", "index_outbox", ["job_id"])
    op.create_index(
        "ix_index_outbox_publish_status",
        "index_outbox",
        ["publish_status", "created_at"],
    )
    op.create_table(
        "graph_projection",
        sa.Column("projection_id", sa.String(64), primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=False),
        sa.Column("entity_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("projected_at", mysql.DATETIME(fsp=6)),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "entity_version",
            name="uq_graph_projection_entity_version",
        ),
    )
    op.add_column("diagnosis_run", sa.Column("diagnosis_template_id", sa.String(128)))
    op.add_column("diagnosis_run", sa.Column("diagnosis_template_version", sa.String(32)))
    op.add_column("diagnosis_run", sa.Column("alarm_category", sa.String(64)))


def downgrade() -> None:
    op.drop_column("diagnosis_run", "alarm_category")
    op.drop_column("diagnosis_run", "diagnosis_template_version")
    op.drop_column("diagnosis_run", "diagnosis_template_id")
    op.drop_table("graph_projection")
    op.drop_table("index_outbox")
    op.drop_table("index_job")
    op.drop_column("maintenance_ticket", "index_generation")
