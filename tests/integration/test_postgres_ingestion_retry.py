from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from automotive_quality.domains.work_orders.ingestion import (
    DatasetVersionConflict,
    IngestionDisposition,
    ingest_generated_dataset,
)
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.sources.synthetic import generate_dataset


def _postgres_engine():
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL integration database is not configured")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        if connection.exec_driver_sql("select current_database()").scalar_one() != "automotive_verify":
            pytest.fail("B2 integration tests require the isolated automotive_verify database")
    return engine


def _version() -> str:
    return f"pg-b2-{uuid4().hex[:16]}"


def _counts(session: Session, version_id: str) -> dict[str, int]:
    return {
        "versions": session.scalar(select(func.count()).select_from(models.DatasetVersion).where(
            models.DatasetVersion.dataset_version_id == version_id
        )),
        "snapshots": session.scalar(select(func.count()).select_from(models.WorkOrderSnapshot).where(
            models.WorkOrderSnapshot.dataset_version_id == version_id
        )),
        "runs": session.scalar(select(func.count()).select_from(models.IngestionRun).where(
            models.IngestionRun.dataset_version_id == version_id
        )),
    }


@pytest.mark.postgres
def test_postgres_identical_retry_is_idempotent() -> None:
    engine = _postgres_engine()
    version = _version()
    version_id = f"DSV-{version}"
    data = generate_dataset(rows=100, seed=211, defect_rate=0)
    try:
        with Session(engine) as session:
            created = ingest_generated_dataset(session, data, version=version)
            retried = ingest_generated_dataset(session, deepcopy(data), version=version)
            assert (created.disposition, retried.disposition) == (
                IngestionDisposition.CREATED,
                IngestionDisposition.ALREADY_INGESTED,
            )
            assert created.run_id == retried.run_id
        with Session(engine) as session:
            assert _counts(session, version_id) == {"versions": 1, "snapshots": 100, "runs": 1}
            attempts = session.scalars(select(models.IngestionAttempt).where(
                models.IngestionAttempt.dataset_version_reference == version
            ).order_by(models.IngestionAttempt.started_at)).all()
            assert [attempt.status for attempt in attempts] == ["SUCCEEDED", "ALREADY_INGESTED"]
            assert {attempt.ingestion_run_id for attempt in attempts} == {created.run_id}
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgres_conflicting_retry_preserves_original() -> None:
    engine = _postgres_engine()
    version = _version()
    version_id = f"DSV-{version}"
    original = generate_dataset(rows=100, seed=223, defect_rate=0)
    changed = generate_dataset(rows=100, seed=227, defect_rate=0)
    try:
        with Session(engine) as session:
            created = ingest_generated_dataset(session, original, version=version)
            original_hash = session.get(models.DatasetVersion, created.dataset_version_id).source_content_hash
            original_ids = set(session.scalars(select(models.WorkOrderSnapshot.work_order_id).where(
                models.WorkOrderSnapshot.dataset_version_id == version_id
            )))
            with pytest.raises(DatasetVersionConflict):
                ingest_generated_dataset(session, changed, version=version)
        with Session(engine) as session:
            assert session.get(models.DatasetVersion, version_id).source_content_hash == original_hash
            assert set(session.scalars(select(models.WorkOrderSnapshot.work_order_id).where(
                models.WorkOrderSnapshot.dataset_version_id == version_id
            ))) == original_ids
            assert _counts(session, version_id) == {"versions": 1, "snapshots": 100, "runs": 1}
            assert set(session.scalars(select(models.IngestionAttempt.status).where(
                models.IngestionAttempt.dataset_version_reference == version
            ))) == {"SUCCEEDED", "VERSION_CONFLICT"}
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgres_concurrent_identical_ingestion_has_one_successful_run() -> None:
    engine = _postgres_engine()
    version = _version()
    version_id = f"DSV-{version}"
    data = generate_dataset(rows=100, seed=229, defect_rate=0)
    barrier = Barrier(2)

    def ingest() -> IngestionDisposition:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            return ingest_generated_dataset(session, deepcopy(data), version=version).disposition

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            dispositions = list(executor.map(lambda _: ingest(), range(2)))
        assert set(dispositions) == {IngestionDisposition.CREATED, IngestionDisposition.ALREADY_INGESTED}
        with Session(engine) as session:
            assert _counts(session, version_id) == {"versions": 1, "snapshots": 100, "runs": 1}
            statuses = list(session.scalars(select(models.IngestionAttempt.status).where(
                models.IngestionAttempt.dataset_version_reference == version
            )))
            assert sorted(statuses) == ["ALREADY_INGESTED", "SUCCEEDED"]
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgres_business_failure_rolls_back_but_audit_survives(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _postgres_engine()
    version = _version()
    version_id = f"DSV-{version}"
    data = generate_dataset(rows=100, seed=233, defect_rate=0)
    try:
        with Session(engine) as session:
            original_flush = session.flush

            def fail_during_snapshots(*args, **kwargs) -> None:
                if any(isinstance(item, models.WorkOrderSnapshot) for item in session.new):
                    raise SQLAlchemyError("controlled database failure; password=must-not-persist")
                original_flush(*args, **kwargs)

            monkeypatch.setattr(session, "flush", fail_during_snapshots)
            with pytest.raises(SQLAlchemyError, match="controlled database failure"):
                ingest_generated_dataset(session, data, version=version)
        with Session(engine) as session:
            assert _counts(session, version_id) == {"versions": 0, "snapshots": 0, "runs": 0}
            attempts = session.scalars(select(models.IngestionAttempt).where(
                models.IngestionAttempt.dataset_version_reference == version
            )).all()
            assert len(attempts) == 1
            assert attempts[0].status == "FAILED"
            assert attempts[0].failure_stage == "work_order_snapshots"
            assert attempts[0].error_category == "DATABASE_ERROR"
            assert "must-not-persist" not in (attempts[0].sanitized_error or "")
    finally:
        engine.dispose()
