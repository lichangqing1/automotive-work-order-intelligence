"""add repeat-safe ingestion identity and durable attempt audit

Revision ID: 20261111_0003
Revises: 20261016_0002
"""

import sqlalchemy as sa
from alembic import op

revision = "20261111_0003"
down_revision = "20261016_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dataset_versions", sa.Column("source_content_hash", sa.String(length=64), nullable=True))
    op.add_column("dataset_versions", sa.Column("source_hash_version", sa.String(length=32), nullable=True))
    op.create_index(
        "uq_ingestion_runs_dataset_version_id",
        "ingestion_runs",
        ["dataset_version_id"],
        unique=True,
    )
    op.create_table(
        "ingestion_attempts",
        sa.Column("attempt_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_version_reference", sa.String(length=64), nullable=False),
        sa.Column("dataset_version_id", sa.String(length=36), nullable=True),
        sa.Column("source_content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_hash_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_stage", sa.String(length=64), nullable=True),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("sanitized_error", sa.Text(), nullable=True),
        sa.Column("source_rows", sa.Integer(), nullable=False),
        sa.Column("ingested_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingestion_run_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("attempt_id"),
    )
    op.create_index("ix_ingestion_attempts_dataset_id", "ingestion_attempts", ["dataset_id"])
    op.create_index(
        "ix_ingestion_attempts_dataset_version_reference",
        "ingestion_attempts",
        ["dataset_version_reference"],
    )
    op.create_index("ix_ingestion_attempts_dataset_version_id", "ingestion_attempts", ["dataset_version_id"])
    op.create_index("ix_ingestion_attempts_source_content_hash", "ingestion_attempts", ["source_content_hash"])
    op.create_index("ix_ingestion_attempts_status", "ingestion_attempts", ["status"])
    op.create_index(
        "ix_ingestion_attempts_version_status",
        "ingestion_attempts",
        ["dataset_version_reference", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_attempts_version_status", table_name="ingestion_attempts")
    op.drop_index("ix_ingestion_attempts_status", table_name="ingestion_attempts")
    op.drop_index("ix_ingestion_attempts_source_content_hash", table_name="ingestion_attempts")
    op.drop_index("ix_ingestion_attempts_dataset_version_id", table_name="ingestion_attempts")
    op.drop_index("ix_ingestion_attempts_dataset_version_reference", table_name="ingestion_attempts")
    op.drop_index("ix_ingestion_attempts_dataset_id", table_name="ingestion_attempts")
    op.drop_table("ingestion_attempts")
    op.drop_index("uq_ingestion_runs_dataset_version_id", table_name="ingestion_runs")
    op.drop_column("dataset_versions", "source_hash_version")
    op.drop_column("dataset_versions", "source_content_hash")
