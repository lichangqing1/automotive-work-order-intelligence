"""add durable AI operation idempotency

Revision ID: 20261112_0006
Revises: 20261111_0005
"""

import sqlalchemy as sa
from alembic import op

revision = "20261112_0006"
down_revision = "20261111_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_operations",
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("principal_id", sa.String(length=128), nullable=False),
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column("target_resource", sa.String(length=256), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("owner_token", sa.String(length=64), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("ai_run_id", sa.String(length=36), nullable=True),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('RUNNING', 'SUCCEEDED', 'FAILED', 'AMBIGUOUS')",
            name="ck_ai_operations_state",
        ),
        sa.CheckConstraint(
            "(state = 'RUNNING' AND completed_at IS NULL) OR "
            "(state IN ('SUCCEEDED', 'FAILED', 'AMBIGUOUS') AND completed_at IS NOT NULL)",
            name="ck_ai_operations_terminal_timestamp",
        ),
        sa.CheckConstraint(
            "state != 'SUCCEEDED' OR response_payload IS NOT NULL",
            name="ck_ai_operations_success_response",
        ),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint(
            "principal_id", "operation_type", "target_resource", "idempotency_key",
            name="uq_ai_operations_scope_key",
        ),
    )
    op.create_index("ix_ai_operations_principal_id", "ai_operations", ["principal_id"])
    op.create_index("ix_ai_operations_state", "ai_operations", ["state"])
    op.create_index("ix_ai_operations_ai_run_id", "ai_operations", ["ai_run_id"])
    op.add_column("review_requests", sa.Column("ai_operation_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_review_requests_ai_operation_id", "review_requests", "ai_operations",
        ["ai_operation_id"], ["operation_id"],
    )
    op.create_index(
        "ix_review_requests_ai_operation_id", "review_requests", ["ai_operation_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_review_requests_ai_operation_id", table_name="review_requests")
    op.drop_constraint("fk_review_requests_ai_operation_id", "review_requests", type_="foreignkey")
    op.drop_column("review_requests", "ai_operation_id")
    op.drop_index("ix_ai_operations_ai_run_id", table_name="ai_operations")
    op.drop_index("ix_ai_operations_state", table_name="ai_operations")
    op.drop_index("ix_ai_operations_principal_id", table_name="ai_operations")
    op.drop_table("ai_operations")
