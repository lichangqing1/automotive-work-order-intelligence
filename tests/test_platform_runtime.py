from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from automotive_quality.application.runtime import PlatformRuntime, database_kpis
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.sources.synthetic import generate_dataset


def test_enterprise_runtime_persists_ingestion_dq_and_reconciliation() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    data = generate_dataset(rows=500, seed=42, defect_rate=0.04)
    with Session(engine) as session:
        summary = PlatformRuntime(session).execute(data, "configs/enterprise_data_quality_rules.yaml", dataset_version="runtime-test")
        session.commit()
        assert summary.reconciliation.passed
        assert session.scalar(select(func.count()).select_from(models.DQRun)) == 1
        assert session.scalar(select(func.count()).select_from(models.DQResult)) == 10
        assert session.scalar(select(func.count()).select_from(models.DQRuleVersion)) == 10
        assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == summary.ingestion.ingested_rows
        assert session.scalar(select(func.count()).select_from(models.ResolutionHistory)) > 0
        assert summary.publication_quality_passed
        assert summary.defect_detection_passed
        assert summary.final_gate_passed
        assert database_kpis(session)["total_work_orders"] == summary.ingestion.ingested_rows


def test_database_kpi_exposes_db_api_consistency_target() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert database_kpis(session) == {"total_work_orders": 0, "ota_work_orders": 0, "open_backlog": 0}
