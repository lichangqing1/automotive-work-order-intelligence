"""record authenticated actors for governed API mutations

Revision ID: 20261111_0005
Revises: 20261111_0004
"""

import sqlalchemy as sa
from alembic import op

revision = "20261111_0005"
down_revision = "20261111_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "requirement_versions",
        sa.Column("created_by_principal_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_requirement_versions_created_by_principal_id",
        "requirement_versions",
        ["created_by_principal_id"],
    )
    op.add_column(
        "test_case_versions",
        sa.Column("generated_by_principal_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_test_case_versions_generated_by_principal_id",
        "test_case_versions",
        ["generated_by_principal_id"],
    )
    op.add_column(
        "test_runs",
        sa.Column("submitted_by_principal_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_test_runs_submitted_by_principal_id",
        "test_runs",
        ["submitted_by_principal_id"],
    )
    op.add_column(
        "external_issue_links",
        sa.Column("last_retry_by_principal_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_external_issue_links_last_retry_by_principal_id",
        "external_issue_links",
        ["last_retry_by_principal_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_external_issue_links_last_retry_by_principal_id",
        table_name="external_issue_links",
    )
    op.drop_column("external_issue_links", "last_retry_by_principal_id")
    op.drop_index("ix_test_runs_submitted_by_principal_id", table_name="test_runs")
    op.drop_column("test_runs", "submitted_by_principal_id")
    op.drop_index(
        "ix_test_case_versions_generated_by_principal_id",
        table_name="test_case_versions",
    )
    op.drop_column("test_case_versions", "generated_by_principal_id")
    op.drop_index(
        "ix_requirement_versions_created_by_principal_id",
        table_name="requirement_versions",
    )
    op.drop_column("requirement_versions", "created_by_principal_id")
