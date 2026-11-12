from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier

import pytest
from conftest import TEST_AUTH_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.application.runtime import PlatformRuntime, database_kpis
from automotive_quality.domains.work_orders.ingestion import (
    DatasetVersionConflict,
    IngestionDisposition,
    dataset_content_hash,
    ingest_generated_dataset,
)
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.sources.synthetic import WorkOrderDataset, generate_dataset

RULES = "configs/enterprise_data_quality_rules.yaml"


def _engine(url: str = "sqlite+pysqlite:///:memory:"):
    kwargs = {"connect_args": {"check_same_thread": False, "timeout": 10}}
    if url.endswith(":memory:"):
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=10000")
        if not url.endswith(":memory:"):
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def retry_engine():
    engine = _engine()
    yield engine
    engine.dispose()


def _copy(data: WorkOrderDataset) -> WorkOrderDataset:
    return WorkOrderDataset(
        data.work_orders.copy(deep=True),
        data.vehicles.copy(deep=True),
        data.ota_releases.copy(deep=True),
        data.diagnostic_events.copy(deep=True),
        set(data.injected_defect_rows),
    )


def test_initial_ingestion_and_identical_retry_are_idempotent(retry_engine) -> None:
    data = generate_dataset(rows=100, seed=101, defect_rate=0)
    with Session(retry_engine) as session:
        created = ingest_generated_dataset(session, data, version="retry-v1")
        retried = ingest_generated_dataset(session, deepcopy(data), version="retry-v1")

        assert created.disposition == IngestionDisposition.CREATED
        assert retried.disposition == IngestionDisposition.ALREADY_INGESTED
        assert retried.run_id == created.run_id
        assert session.scalar(select(func.count()).select_from(models.DatasetVersion)) == 1
        assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 100
        assert session.scalar(select(func.count()).select_from(models.IngestionRun)) == 1
        attempts = session.scalars(select(models.IngestionAttempt).order_by(models.IngestionAttempt.started_at)).all()
        assert [item.status for item in attempts] == ["SUCCEEDED", "ALREADY_INGESTED"]
        assert all(item.ingestion_run_id == created.run_id for item in attempts)


def test_same_version_different_content_is_rejected_without_mutation(retry_engine) -> None:
    original = generate_dataset(rows=100, seed=103, defect_rate=0)
    changed = generate_dataset(rows=100, seed=107, defect_rate=0)
    with Session(retry_engine) as session:
        created = ingest_generated_dataset(session, original, version="conflict-v1")
        version = session.get(models.DatasetVersion, created.dataset_version_id)
        assert version is not None
        original_hash = version.source_content_hash
        original_ids = set(session.scalars(select(models.WorkOrderSnapshot.work_order_id)))

        with pytest.raises(DatasetVersionConflict, match="different immutable source content"):
            ingest_generated_dataset(session, changed, version="conflict-v1")

        session.expire_all()
        version = session.get(models.DatasetVersion, created.dataset_version_id)
        assert version is not None and version.source_content_hash == original_hash
        assert set(session.scalars(select(models.WorkOrderSnapshot.work_order_id))) == original_ids
        assert session.scalar(select(func.count()).select_from(models.IngestionRun)) == 1
        conflict = session.scalar(select(models.IngestionAttempt).where(
            models.IngestionAttempt.status == "VERSION_CONFLICT"
        ))
        assert conflict is not None
        assert conflict.sanitized_error == "Dataset version already exists with different immutable source content"


def test_identical_content_is_allowed_under_a_different_version(retry_engine) -> None:
    data = generate_dataset(rows=100, seed=109, defect_rate=0)
    with Session(retry_engine) as session:
        first = ingest_generated_dataset(session, data, version="copy-v1")
        second = ingest_generated_dataset(session, data, version="copy-v2")

        assert first.disposition == second.disposition == IngestionDisposition.CREATED
        assert first.dataset_version_id != second.dataset_version_id
        versions = session.scalars(select(models.DatasetVersion)).all()
        assert len(versions) == 2
        assert len({item.source_content_hash for item in versions}) == 1
        assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 200


def test_source_fingerprint_is_order_independent_but_duplicate_sensitive() -> None:
    original = generate_dataset(rows=100, seed=113, defect_rate=0)
    reordered = WorkOrderDataset(
        original.work_orders.sample(frac=1, random_state=1).reset_index(drop=True),
        original.vehicles.sample(frac=1, random_state=2).reset_index(drop=True),
        original.ota_releases.sample(frac=1, random_state=3).reset_index(drop=True),
        original.diagnostic_events.sample(frac=1, random_state=4).reset_index(drop=True),
        set(original.injected_defect_rows),
    )
    duplicate_orders = original.work_orders.copy(deep=True)
    duplicate_orders.loc[duplicate_orders.index[-1]] = duplicate_orders.iloc[0]
    duplicated = WorkOrderDataset(
        duplicate_orders,
        original.vehicles.copy(deep=True),
        original.ota_releases.copy(deep=True),
        original.diagnostic_events.copy(deep=True),
        set(original.injected_defect_rows),
    )

    assert dataset_content_hash(original) == dataset_content_hash(reordered)
    assert dataset_content_hash(original) != dataset_content_hash(duplicated)


def test_changed_rejected_source_cannot_match_unchanged_curated_output(retry_engine) -> None:
    curated = generate_dataset(rows=100, seed=127, defect_rate=0)
    source_one = _copy(curated)
    source_two = _copy(curated)
    source_two.work_orders.loc[source_two.work_orders.index[-1], "description"] = "changed quarantined payload"
    with Session(retry_engine) as session:
        ingest_generated_dataset(
            session,
            curated,
            version="quarantine-v1",
            rejected_rows=1,
            source_row_count=101,
            source_content_hash=dataset_content_hash(source_one),
        )
        with pytest.raises(DatasetVersionConflict):
            ingest_generated_dataset(
                session,
                curated,
                version="quarantine-v1",
                rejected_rows=1,
                source_row_count=101,
                source_content_hash=dataset_content_hash(source_two),
            )
        assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 100


def test_partial_failure_rolls_back_business_data_and_keeps_sanitized_audit(
    retry_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = generate_dataset(rows=100, seed=131, defect_rate=0)
    with Session(retry_engine) as session:
        original_flush = session.flush

        def fail_during_snapshots(*args, **kwargs) -> None:
            if any(isinstance(item, models.WorkOrderSnapshot) for item in session.new):
                raise SQLAlchemyError("password=secret-value api_key=private-value")
            original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", fail_during_snapshots)
        with pytest.raises(SQLAlchemyError, match="secret-value"):
            ingest_generated_dataset(session, data, version="failed-v1")

        assert session.get(models.DatasetVersion, "DSV-failed-v1") is None
        assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 0
        assert session.scalar(select(func.count()).select_from(models.IngestionRun)) == 0
        attempt = session.scalar(select(models.IngestionAttempt))
        assert attempt is not None and attempt.status == "FAILED"
        assert attempt.failure_stage == "work_order_snapshots"
        assert attempt.error_category == "DATABASE_ERROR"
        assert "secret-value" not in attempt.sanitized_error
        assert "private-value" not in attempt.sanitized_error


def test_safe_retry_after_interrupted_ingestion_succeeds(retry_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    data = generate_dataset(rows=100, seed=137, defect_rate=0)
    with Session(retry_engine) as session:
        original_flush = session.flush
        failed_once = False

        def interrupt_once(*args, **kwargs) -> None:
            nonlocal failed_once
            if not failed_once and any(isinstance(item, models.WorkOrderSnapshot) for item in session.new):
                failed_once = True
                raise SQLAlchemyError("synthetic interruption")
            original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", interrupt_once)
        with pytest.raises(SQLAlchemyError):
            ingest_generated_dataset(session, data, version="interrupt-v1")
        monkeypatch.setattr(session, "flush", original_flush)

        retried = ingest_generated_dataset(session, data, version="interrupt-v1")
        assert retried.disposition == IngestionDisposition.CREATED
        assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 100
        assert session.scalar(select(func.count()).select_from(models.IngestionRun)) == 1
        statuses = session.scalars(select(models.IngestionAttempt.status).order_by(
            models.IngestionAttempt.started_at
        )).all()
        assert statuses == ["FAILED", "SUCCEEDED"]


def test_duplicate_business_ids_fail_atomically_with_durable_attempt(retry_engine) -> None:
    data = generate_dataset(rows=100, seed=139, defect_rate=0)
    data.work_orders.loc[data.work_orders.index[-1], "work_order_id"] = data.work_orders.iloc[0]["work_order_id"]
    with Session(retry_engine) as session:
        with pytest.raises(SQLAlchemyError):
            ingest_generated_dataset(session, data, version="duplicate-v1")
        assert session.scalar(select(func.count()).select_from(models.DatasetVersion)) == 0
        assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 0
        attempt = session.scalar(select(models.IngestionAttempt))
        assert attempt is not None and attempt.status == "FAILED"
        assert attempt.error_category == "DATABASE_CONSTRAINT"


def test_successful_ingestion_owns_its_atomic_commit(retry_engine) -> None:
    data = generate_dataset(rows=100, seed=149, defect_rate=0)
    with Session(retry_engine) as session:
        ingest_generated_dataset(session, data, version="atomic-v1")
        session.rollback()
    with Session(retry_engine) as verify:
        assert verify.get(models.DatasetVersion, "DSV-atomic-v1") is not None
        assert verify.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 100
        assert verify.scalar(select(func.count()).select_from(models.IngestionRun)) == 1


def test_b1_reconciliation_and_identical_v2_retry_remain_stable(retry_engine) -> None:
    first_data = generate_dataset(rows=500, seed=42, defect_rate=0.04)
    second_data = generate_dataset(rows=500, seed=43, defect_rate=0.04)
    with Session(retry_engine) as session:
        runtime = PlatformRuntime(session)
        first = runtime.execute(first_data, RULES, dataset_version="b2-v1")
        session.commit()
        second = runtime.execute(second_data, RULES, dataset_version="b2-v2")
        session.commit()
        retried = runtime.execute(deepcopy(second_data), RULES, dataset_version="b2-v2")
        session.commit()

        assert (first.reconciliation.expected, first.reconciliation.actual) == (480, 480)
        assert (second.reconciliation.expected, second.reconciliation.actual) == (480, 480)
        assert retried.ingestion.disposition == IngestionDisposition.ALREADY_INGESTED
        assert (retried.reconciliation.expected, retried.reconciliation.actual) == (480, 480)
        assert database_kpis(session, "b2-v2")["total_work_orders"] == 480
        assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot).where(
            models.WorkOrderSnapshot.dataset_version_id == "DSV-b2-v2"
        )) == 480
        assert session.scalar(select(func.count()).select_from(models.IngestionRun).where(
            models.IngestionRun.dataset_version_id == "DSV-b2-v2"
        )) == 1


def test_dataset_api_reports_retry_without_exposing_audit_errors(retry_engine) -> None:
    data = generate_dataset(rows=100, seed=151, defect_rate=0)
    with Session(retry_engine) as session:
        ingest_generated_dataset(session, data, version="api-retry-v1")
        ingest_generated_dataset(session, data, version="api-retry-v1")
    previous = app.dependency_overrides.get(database_session)

    def _session_override() -> Iterator[Session]:
        with Session(retry_engine) as session:
            yield session

    app.dependency_overrides[database_session] = _session_override
    try:
        with TestClient(app, headers=TEST_AUTH_HEADERS) as client:
            response = client.get("/api/v1/datasets/api-retry-v1")
    finally:
        if previous is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous

    assert response.status_code == 200
    assert response.json()["ingestion_status"] == "SUCCEEDED"
    assert response.json()["ingestion_attempt_count"] == 2
    assert response.json()["last_ingestion_attempt_status"] == "ALREADY_INGESTED"
    assert "sanitized_error" not in response.json()


def test_concurrent_identical_ingestion_has_one_successful_run(tmp_path: Path) -> None:
    engine = _engine(f"sqlite+pysqlite:///{tmp_path / 'identical-retry.db'}")
    data = generate_dataset(rows=100, seed=157, defect_rate=0)
    barrier = Barrier(2)

    def ingest() -> IngestionDisposition:
        with Session(engine) as session:
            barrier.wait(timeout=5)
            return ingest_generated_dataset(session, deepcopy(data), version="concurrent-v1").disposition

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            dispositions = list(executor.map(lambda _: ingest(), range(2)))
        assert set(dispositions) == {IngestionDisposition.CREATED, IngestionDisposition.ALREADY_INGESTED}
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(models.DatasetVersion)) == 1
            assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 100
            assert session.scalar(select(func.count()).select_from(models.IngestionRun)) == 1
            assert session.scalar(select(func.count()).select_from(models.IngestionAttempt)) == 2
    finally:
        engine.dispose()


def test_concurrent_conflicting_ingestion_preserves_one_immutable_version(tmp_path: Path) -> None:
    engine = _engine(f"sqlite+pysqlite:///{tmp_path / 'conflicting-retry.db'}")
    datasets = [
        generate_dataset(rows=100, seed=163, defect_rate=0),
        generate_dataset(rows=100, seed=167, defect_rate=0),
    ]
    barrier = Barrier(2)

    def ingest(data: WorkOrderDataset) -> str:
        with Session(engine) as session:
            barrier.wait(timeout=5)
            try:
                return str(ingest_generated_dataset(session, data, version="concurrent-conflict").disposition)
            except DatasetVersionConflict:
                return "VERSION_CONFLICT"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(ingest, datasets))
        assert sorted(outcomes) == ["CREATED", "VERSION_CONFLICT"]
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(models.DatasetVersion)) == 1
            assert session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot)) == 100
            assert session.scalar(select(func.count()).select_from(models.IngestionRun)) == 1
            statuses = set(session.scalars(select(models.IngestionAttempt.status)))
            assert statuses == {"SUCCEEDED", "VERSION_CONFLICT"}
    finally:
        engine.dispose()
