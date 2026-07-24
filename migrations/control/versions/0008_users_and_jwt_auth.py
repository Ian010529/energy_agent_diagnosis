"""Phase 7.5 users and rotating JWT refresh sessions.

Revision ID: 0008_phase7_5
Revises: 0007_phase7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0008_phase7_5"
down_revision: str | Sequence[str] | None = "0007_phase7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("username_normalized", sa.String(128), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), unique=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", mysql.DATETIME(fsp=6)),
        sa.Column("last_login_at", mysql.DATETIME(fsp=6)),
        sa.Column("last_password_changed_at", mysql.DATETIME(fsp=6)),
        sa.Column("created_by", sa.String(64)),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
    )
    op.create_table(
        "auth_refresh_session",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("app_user.user_id"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("token_family_id", sa.String(64), nullable=False),
        sa.Column("jti", sa.String(64), nullable=False, unique=True),
        sa.Column("rotated_from_session_id", sa.String(64)),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_used_at", mysql.DATETIME(fsp=6)),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6)),
        sa.Column("revoke_reason", sa.String(128)),
        sa.Column("ip_hash", sa.String(64)),
        sa.Column("user_agent_hash", sa.String(64)),
    )
    op.create_index(
        "ix_auth_refresh_user_revoked", "auth_refresh_session", ["user_id", "revoked_at"]
    )
    op.create_index("ix_auth_refresh_family", "auth_refresh_session", ["token_family_id"])
    op.create_index("ix_auth_refresh_expires", "auth_refresh_session", ["expires_at"])


def downgrade() -> None:
    op.drop_table("auth_refresh_session")
    op.drop_table("app_user")
