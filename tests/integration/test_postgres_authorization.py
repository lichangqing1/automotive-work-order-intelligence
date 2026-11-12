from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import Event
from uuid import uuid4

import pytest
from conftest import TEST_AUTH_HEADERS, TEST_READER_HEADERS, TEST_REVIEWER_HEADERS
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from automotive_quality.api.auth import AuthenticatedPrincipal
from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.api.v1 import _bind_reviewer
from automotive_quality.infrastructure.database import models


def _engine():
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL integration database is not configured")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        if connection.exec_driver_sql("select current_database()").scalar_one() != "automotive_verify":
            pytest.fail("C1.3 integration tests require the isolated automotive_verify database")
    return engine


@pytest.mark.postgres
def test_postgres_authorization_and_actor_audit_are_durable() -> None:
    engine = _engine()
    suffix = uuid4().hex[:12]
    dataset_id = f"DS-AUTHZ-{suffix}"
    dataset_version_id = f"DSV-AUTHZ-{suffix}"
    requirement_id = f"REQV-AUTHZ-{suffix}"
    case_id = f"TC-AUTHZ-{suffix}"
    version_id = f"TCV-AUTHZ-{suffix}"
    review_id = f"REV-AUTHZ-{suffix}"

    with Session(engine) as setup:
        setup.add(models.Dataset(dataset_id=dataset_id, name=f"authz-{suffix}", source_type="SYNTHETIC"))
        setup.add(models.DatasetVersion(
            dataset_version_id=dataset_version_id,
            dataset_id=dataset_id,
            version=f"authz-{suffix}",
            row_count=0,
            content_hash="d" * 64,
            source_content_hash="d" * 64,
            source_hash_version="sha256-v1",
        ))
        setup.add(models.RequirementVersion(
            requirement_version_id=requirement_id,
            requirement_id=f"REQ-AUTHZ-{suffix}",
            version=1,
            external_system="LOCAL",
            external_reference=f"AUTHZ-{suffix}",
            summary="PostgreSQL authorization fixture",
            description="PostgreSQL authorization fixture",
            acceptance_criteria="PostgreSQL authorization fixture",
            content_hash="r" * 64,
            created_by_principal_id="pytest-operator",
        ))
        setup.add(models.TestCase(
            test_case_id=case_id,
            suite=f"REQ-{suffix}",
            title="PostgreSQL authorization fixture",
            severity="P1",
            specification={"expected_result": "expected"},
            review_status="APPROVED",
        ))
        setup.add(models.TestCaseVersion(
            test_case_version_id=version_id,
            test_case_id=case_id,
            version=1,
            requirement_version_id=requirement_id,
            source_ai_run_id=None,
            generated_by_principal_id="pytest-operator",
            status="APPROVED",
            content={"expected_result": "expected"},
        ))
        setup.add(models.ReviewRequest(
            review_id=review_id,
            artifact_type="TEST_CASE_BATCH",
            artifact_ids=[version_id],
            status="REVIEW_REQUIRED",
            external_system="LOCAL",
        ))
        setup.commit()

    def session_override() -> Iterator[Session]:
        with Session(engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    previous = app.dependency_overrides.get(database_session)
    app.dependency_overrides[database_session] = session_override
    try:
        with TestClient(app, headers=TEST_READER_HEADERS) as reader:
            assert reader.post(f"/api/v1/reviews/{review_id}/start").status_code == 403
            assert reader.post("/api/v1/test-runs", json={}).status_code == 403
        with TestClient(app, headers=TEST_REVIEWER_HEADERS) as reviewer:
            assert reviewer.post(f"/api/v1/reviews/{review_id}/start").status_code == 200
        with TestClient(app, headers=TEST_AUTH_HEADERS) as operator:
            response = operator.post("/api/v1/test-runs", json={
                "requirement_version_id": requirement_id,
                "test_case_version_ids": [version_id],
                "dataset_version": dataset_version_id,
                "actuals": {version_id: "expected"},
            })
            assert response.status_code == 200
            run_id = response.json()["test_run_id"]
    finally:
        if previous is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous

    with Session(engine) as verify:
        review = verify.get(models.ReviewRequest, review_id)
        run = verify.get(models.TestRun, run_id)
        result = verify.scalar(select(models.TestResult).where(models.TestResult.test_run_id == run_id))
        assert review is not None and review.reviewer == "pytest-reviewer"
        assert run is not None and run.submitted_by_principal_id == "pytest-operator"
        assert result is not None and result.evidence["submitted_by_principal_id"] == "pytest-operator"
    engine.dispose()


@pytest.mark.postgres
def test_postgres_concurrent_reviewer_assignment_cannot_be_taken_over() -> None:
    engine = _engine()
    suffix = uuid4().hex[:12]
    requirement_id = f"REQV-RACE-{suffix}"
    case_id = f"TC-RACE-{suffix}"
    version_id = f"TCV-RACE-{suffix}"
    review_id = f"REV-RACE-{suffix}"
    with Session(engine) as setup:
        setup.add(models.RequirementVersion(
            requirement_version_id=requirement_id,
            requirement_id=f"REQ-RACE-{suffix}",
            version=1,
            external_system="LOCAL",
            external_reference=f"RACE-{suffix}",
            summary="Reviewer concurrency fixture",
            description="Reviewer concurrency fixture",
            acceptance_criteria="Reviewer concurrency fixture",
            content_hash="c" * 64,
            created_by_principal_id="pytest-operator",
        ))
        setup.add(models.TestCase(
            test_case_id=case_id,
            suite=f"REQ-{suffix}",
            title="Reviewer concurrency fixture",
            severity="P1",
            specification={"expected_result": "expected"},
            review_status="REVIEW_REQUIRED",
        ))
        setup.add(models.TestCaseVersion(
            test_case_version_id=version_id,
            test_case_id=case_id,
            version=1,
            requirement_version_id=requirement_id,
            source_ai_run_id=None,
            generated_by_principal_id="pytest-operator",
            status="REVIEW_REQUIRED",
            content={"expected_result": "expected"},
        ))
        setup.add(models.ReviewRequest(
            review_id=review_id,
            artifact_type="TEST_CASE_BATCH",
            artifact_ids=[version_id],
            status="REVIEW_REQUIRED",
            external_system="LOCAL",
        ))
        setup.commit()

    first = AuthenticatedPrincipal(
        principal_id="reviewer-one",
        category="test",
        roles=frozenset({"reviewer"}),
        key_id="reviewer-one-v1",
    )
    second = AuthenticatedPrincipal(
        principal_id="reviewer-two",
        category="test",
        roles=frozenset({"reviewer"}),
        key_id="reviewer-two-v1",
    )
    second_started = Event()

    def competing_assignment() -> int:
        with Session(engine) as session:
            second_started.set()
            try:
                _bind_reviewer(session, review_id, second)
                session.commit()
                return 200
            except HTTPException as exc:
                session.rollback()
                return exc.status_code

    with Session(engine) as first_session:
        _bind_reviewer(first_session, review_id, first)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(competing_assignment)
            assert second_started.wait(timeout=2)
            with pytest.raises(FutureTimeoutError):
                future.result(timeout=0.25)
            first_session.commit()
            assert future.result(timeout=2) == 403

    with Session(engine) as verify:
        review = verify.get(models.ReviewRequest, review_id)
        assert review is not None and review.reviewer == "reviewer-one"
    engine.dispose()
