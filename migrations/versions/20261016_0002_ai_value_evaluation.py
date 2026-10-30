"""AI value experiment metadata and review measurements

Revision ID: 20261016_0002
Revises: 20261015_0001
"""
import sqlalchemy as sa
from alembic import op

revision = "20261016_0002"
down_revision = "20261015_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("review_requests", sa.Column("review_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("review_requests", sa.Column("active_review_seconds", sa.Float(), nullable=True))
    op.add_column("review_requests", sa.Column("was_modified", sa.Boolean(), nullable=True))
    op.add_column("review_requests", sa.Column("rejection_reasons", sa.JSON(), nullable=True))
    op.add_column("review_requests", sa.Column("validated_coverage", sa.JSON(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("experiment_group", sa.String(length=64), nullable=True))
    op.add_column("evaluation_runs", sa.Column("variant", sa.String(length=32), nullable=True))
    op.add_column("evaluation_runs", sa.Column("baseline_type", sa.String(length=64), nullable=True))
    op.add_column("evaluation_runs", sa.Column("provider", sa.String(length=64), nullable=True))
    op.add_column("evaluation_runs", sa.Column("model", sa.String(length=128), nullable=True))
    op.add_column("evaluation_runs", sa.Column("prompt_version", sa.String(length=32), nullable=True))
    op.add_column("evaluation_runs", sa.Column("prompt_hash", sa.String(length=64), nullable=True))
    op.add_column("evaluation_runs", sa.Column("dataset_hash", sa.String(length=64), nullable=True))
    op.add_column("evaluation_runs", sa.Column("run_number", sa.Integer(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("configuration", sa.JSON(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("raw_outputs", sa.JSON(), nullable=True))
    op.add_column("evaluation_runs", sa.Column("summary", sa.JSON(), nullable=True))
    op.add_column("evaluation_metrics", sa.Column("sample_id", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_evaluation_runs_experiment_group"), "evaluation_runs", ["experiment_group"], unique=False)
    op.create_index(op.f("ix_evaluation_runs_variant"), "evaluation_runs", ["variant"], unique=False)
    op.create_index(op.f("ix_evaluation_metrics_sample_id"), "evaluation_metrics", ["sample_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_metrics_sample_id"), table_name="evaluation_metrics")
    op.drop_index(op.f("ix_evaluation_runs_variant"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_experiment_group"), table_name="evaluation_runs")
    op.drop_column("evaluation_metrics", "sample_id")
    for column in ("summary", "raw_outputs", "configuration", "run_number", "dataset_hash", "prompt_hash", "prompt_version", "model", "provider", "baseline_type", "variant", "experiment_group"):
        op.drop_column("evaluation_runs", column)
    for column in ("validated_coverage", "rejection_reasons", "was_modified", "active_review_seconds", "review_started_at"):
        op.drop_column("review_requests", column)
