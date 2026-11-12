"""make AI run failure audit state explicit

Revision ID: 20261111_0004
Revises: 20261111_0003
"""

import sqlalchemy as sa
from alembic import op

revision = "20261111_0004"
down_revision = "20261111_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_runs", sa.Column("failure_stage", sa.String(length=64), nullable=True))
    op.add_column("ai_runs", sa.Column("error_category", sa.String(length=64), nullable=True))
    op.add_column("ai_runs", sa.Column("correlation_id", sa.String(length=64), nullable=True))
    op.add_column("ai_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ai_runs_correlation_id", "ai_runs", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_runs_correlation_id", table_name="ai_runs")
    op.drop_column("ai_runs", "completed_at")
    op.drop_column("ai_runs", "correlation_id")
    op.drop_column("ai_runs", "error_category")
    op.drop_column("ai_runs", "failure_stage")
