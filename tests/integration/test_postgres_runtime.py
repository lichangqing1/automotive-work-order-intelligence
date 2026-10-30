import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from automotive_quality.application.runtime import PlatformRuntime
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.session import session_scope
from automotive_quality.infrastructure.sources.synthetic import generate_dataset


@pytest.mark.postgres
def test_real_postgres_runtime_persists_all_run_types() -> None:
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL integration database is not configured")
    version = f"pg-{uuid4().hex[:8]}"
    with session_scope(database_url) as session:
        summary = PlatformRuntime(session).execute(
            generate_dataset(rows=100, seed=73, defect_rate=0.05),
            "configs/enterprise_data_quality_rules.yaml",
            dataset_version=version,
        )
        assert summary.reconciliation.passed
        assert session.scalar(select(func.count()).select_from(models.IngestionRun)) >= 1
        assert session.scalar(select(func.count()).select_from(models.DQRun)) >= 1
