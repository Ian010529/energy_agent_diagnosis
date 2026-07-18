"""Phase 3 complete RAG storage.

Revision ID: 0003_phase3
Revises: 0002_phase2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003_phase3"
down_revision: str | Sequence[str] | None = "0002_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "manual_document",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("doc_id", sa.String(128), nullable=False),
        sa.Column("document_name", sa.String(255), nullable=False),
        sa.Column("object_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("device_type", sa.String(64), nullable=False),
        sa.Column("device_model", sa.String(128)),
        sa.Column("manufacturer", sa.String(128)),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("effective", sa.Boolean(), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("chunking_version", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(128)),
        sa.Column("embedding_dimension", sa.Integer()),
        sa.Column("index_status", sa.String(32), nullable=False),
        sa.Column("index_error_code", sa.String(64)),
        sa.Column("index_generation", sa.String(64)),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.UniqueConstraint("doc_id", "version", name="uq_manual_document_version"),
    )
    op.create_index("ix_manual_document_doc_id", "manual_document", ["doc_id"])
    for _name, column in (
        ("content_hash", sa.Column("content_hash", sa.String(64))),
        ("chunk_order", sa.Column("chunk_order", sa.Integer(), nullable=False, server_default="0")),
        ("keywords", sa.Column("keywords", sa.JSON())),
        ("embedding_text", sa.Column("embedding_text", sa.Text())),
        ("index_generation", sa.Column("index_generation", sa.String(64))),
        ("embedding_model", sa.Column("embedding_model", sa.String(128))),
        ("embedding_dimension", sa.Column("embedding_dimension", sa.Integer())),
        ("indexed_at", sa.Column("indexed_at", mysql.DATETIME(fsp=6))),
        ("created_at", sa.Column("created_at", mysql.DATETIME(fsp=6))),
        ("updated_at", sa.Column("updated_at", mysql.DATETIME(fsp=6))),
    ):
        op.add_column("manual_chunk", column)
    for _name, column in (
        ("manufacturer", sa.Column("manufacturer", sa.String(128))),
        ("embedding_text", sa.Column("embedding_text", sa.Text())),
        (
            "index_status",
            sa.Column("index_status", sa.String(32), nullable=False, server_default="PENDING"),
        ),
        ("index_error_code", sa.Column("index_error_code", sa.String(64))),
        ("embedding_model", sa.Column("embedding_model", sa.String(128))),
        ("embedding_dimension", sa.Column("embedding_dimension", sa.Integer())),
        ("indexed_at", sa.Column("indexed_at", mysql.DATETIME(fsp=6))),
        ("updated_at", sa.Column("updated_at", mysql.DATETIME(fsp=6))),
    ):
        op.add_column("maintenance_ticket", column)


def downgrade() -> None:
    for column in (
        "manufacturer",
        "embedding_text",
        "index_status",
        "index_error_code",
        "embedding_model",
        "embedding_dimension",
        "indexed_at",
        "updated_at",
    ):
        op.drop_column("maintenance_ticket", column)
    for column in (
        "content_hash",
        "chunk_order",
        "keywords",
        "embedding_text",
        "index_generation",
        "embedding_model",
        "embedding_dimension",
        "indexed_at",
        "created_at",
        "updated_at",
    ):
        op.drop_column("manual_chunk", column)
    op.drop_table("manual_document")
