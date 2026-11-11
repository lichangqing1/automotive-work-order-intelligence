from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.application.runtime import PlatformRuntime, database_kpis, dataset_reconciliation
from automotive_quality.domains.work_orders.ingestion import ingest_generated_dataset
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.database.dataset_versions import UnknownDatasetVersion
from automotive_quality.infrastructure.sources.synthetic import generate_dataset

RULES = "configs/enterprise_data_quality_rules.yaml"


def _engine(url: str = "sqlite+pysqlite:///:memory:"):
    kwargs = {"connect_args": {"check_same_thread": False}}
    if url.endswith(":memory:"):
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def isolation_engine():
    engine = _engine()
    yield engine
    engine.dispose()


def test_audited_sequential_500_row_versions_do_not_cross_contaminate(isolation_engine) -> None:
    with Session(isolation_engine) as session:
        runtime = PlatformRuntime(session)
        first = runtime.execute(generate_dataset(rows=500, seed=42, defect_rate=0.04), RULES, dataset_version="b1-v1")
        session.commit()
        second = runtime.execute(generate_dataset(rows=500, seed=43, defect_rate=0.04), RULES, dataset_version="b1-v2")
        session.commit()

        assert (first.reconciliation.expected, first.reconciliation.actual, first.reconciliation.variance) == (480, 480, 0)
        assert (second.reconciliation.expected, second.reconciliation.actual, second.reconciliation.variance) == (480, 480, 0)
        assert first.reconciliation.passed and second.reconciliation.passed
        assert session.scalar(select(func.count()).select_from(models.WorkOrder)) == 500
        assert database_kpis(session, "b1-v1")["total_work_orders"] == 480
        assert database_kpis(session, "b1-v2")["total_work_orders"] == 480
        first_ids = set(session.scalars(select(models.WorkOrderSnapshot.work_order_id).where(
            models.WorkOrderSnapshot.dataset_version_id == first.ingestion.dataset_version_id
        )))
        second_ids = set(session.scalars(select(models.WorkOrderSnapshot.work_order_id).where(
            models.WorkOrderSnapshot.dataset_version_id == second.ingestion.dataset_version_id
        )))
        assert first_ids & second_ids
        assert session.get(models.DQRun, first.dq_run_id).dataset_version == first.ingestion.dataset_version_id
        assert session.get(models.DQRun, second.dq_run_id).dataset_version == second.ingestion.dataset_version_id


def test_different_row_counts_and_seeds_keep_historical_counts_stable(isolation_engine) -> None:
    with Session(isolation_engine) as session:
        runtime = PlatformRuntime(session)
        first = runtime.execute(generate_dataset(rows=500, seed=11, defect_rate=0.04), RULES, dataset_version="history-v1")
        session.commit()
        before = database_kpis(session, first.ingestion.dataset_version_id)
        second = runtime.execute(generate_dataset(rows=300, seed=99, defect_rate=0.04), RULES, dataset_version="history-v2")
        session.commit()
        after = database_kpis(session, "history-v1")

        assert before == after
        assert first.reconciliation.actual == 480
        assert second.reconciliation.expected == second.reconciliation.actual == 288
        assert database_kpis(session, "history-v2")["total_work_orders"] == 288
        first_run = session.get(models.IngestionRun, first.ingestion.run_id)
        second_run = session.get(models.IngestionRun, second.ingestion.run_id)
        assert (first_run.ingested_rows, first_run.rejected_rows) == (480, 20)
        assert (second_run.ingested_rows, second_run.rejected_rows) == (288, 12)


@pytest.mark.parametrize("extra", [False, True], ids=["missing_clean_record", "unexpected_clean_record"])
def test_real_snapshot_mismatch_fails_reconciliation(isolation_engine, extra: bool) -> None:
    with Session(isolation_engine) as session:
        summary = PlatformRuntime(session).execute(
            generate_dataset(rows=100, seed=17, defect_rate=0), RULES, dataset_version="mismatch-v1"
        )
        session.commit()
        if extra:
            session.add(models.WorkOrderSnapshot(
                dataset_version_id=summary.ingestion.dataset_version_id,
                work_order_id="WO-UNEXPECTED",
                payload={"work_order_id": "WO-UNEXPECTED", "status": "OPEN", "service_type": "OTA"},
                row_hash="f" * 64,
            ))
        else:
            snapshot = session.scalar(select(models.WorkOrderSnapshot).where(
                models.WorkOrderSnapshot.dataset_version_id == summary.ingestion.dataset_version_id
            ))
            assert snapshot is not None
            session.delete(snapshot)
        session.commit()

        result = dataset_reconciliation(session, "mismatch-v1")
        assert result.passed is False
        assert result.variance == (1 if extra else -1)


def test_versioned_api_metrics_and_dataset_detail_match_database(isolation_engine) -> None:
    with Session(isolation_engine) as session:
        summary = PlatformRuntime(session).execute(
            generate_dataset(rows=100, seed=23, defect_rate=0), RULES, dataset_version="api-versioned"
        )
        session.commit()
    previous = app.dependency_overrides.get(database_session)

    def _session_override() -> Iterator[Session]:
        with Session(isolation_engine) as session:
            yield session

    app.dependency_overrides[database_session] = _session_override
    try:
        with TestClient(app) as client:
            metrics = client.get("/api/v1/metrics/overview?dataset_version=api-versioned")
            by_id = client.get(f"/api/v1/metrics/overview?dataset_version={summary.ingestion.dataset_version_id}")
            detail = client.get("/api/v1/datasets/api-versioned")
            unknown = client.get("/api/v1/metrics/overview?dataset_version=missing-version")
    finally:
        if previous is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous

    assert metrics.status_code == by_id.status_code == detail.status_code == 200
    assert metrics.json() == by_id.json()
    assert metrics.json()["scope"] == "DATASET_VERSION"
    assert metrics.json()["total_work_orders"] == 100
    assert detail.json()["source_row_count"] == 100
    assert detail.json()["clean_row_count"] == detail.json()["snapshot_count"] == 100
    assert detail.json()["quarantined_row_count"] == 0
    assert unknown.status_code == 404


def test_unknown_dataset_version_never_falls_back_to_latest(isolation_engine) -> None:
    with Session(isolation_engine) as session:
        PlatformRuntime(session).execute(
            generate_dataset(rows=100, seed=29, defect_rate=0), RULES, dataset_version="known-v1"
        )
        session.commit()
        with pytest.raises(UnknownDatasetVersion):
            database_kpis(session, "unknown-v9")
        with pytest.raises(UnknownDatasetVersion):
            dataset_reconciliation(session, "unknown-v9")


def test_duplicate_business_id_fails_ingestion_and_external_rollback_is_complete(isolation_engine) -> None:
    data = generate_dataset(rows=100, seed=31, defect_rate=0)
    duplicate_id = data.work_orders.iloc[0]["work_order_id"]
    data.work_orders.loc[data.work_orders.index[-1], "work_order_id"] = duplicate_id
    with Session(isolation_engine) as session:
        with pytest.raises(IntegrityError):
            ingest_generated_dataset(session, data, version="duplicate-v1")
        session.rollback()

        assert session.get(models.DatasetVersion, "DSV-duplicate-v1") is None
        assert session.scalar(select(func.count()).select_from(models.IngestionRun)) == 0
        assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 0


def test_interleaved_version_queries_remain_isolated(tmp_path: Path) -> None:
    engine = _engine(f"sqlite+pysqlite:///{tmp_path / 'version-queries.db'}")
    try:
        with Session(engine) as session:
            runtime = PlatformRuntime(session)
            runtime.execute(generate_dataset(rows=100, seed=37, defect_rate=0), RULES, dataset_version="query-v1")
            session.commit()
            runtime.execute(generate_dataset(rows=200, seed=41, defect_rate=0), RULES, dataset_version="query-v2")
            session.commit()

        def query(version: str) -> int:
            with Session(engine) as session:
                return int(database_kpis(session, version)["total_work_orders"])

        versions = ["query-v1", "query-v2"] * 5
        with ThreadPoolExecutor(max_workers=4) as executor:
            counts = list(executor.map(query, versions))
        assert counts == [100, 200] * 5
    finally:
        engine.dispose()
