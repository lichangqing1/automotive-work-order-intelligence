from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from uuid import uuid4

import pytest
from conftest import (
    TEST_ADMIN_HEADERS,
    TEST_AUTH_HEADERS,
    TEST_DUAL_ROLE_HEADERS,
    TEST_READER_HEADERS,
    TEST_REVIEWER_HEADERS,
)
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from automotive_quality.api import v1
from automotive_quality.api.auth import get_bearer_authenticator
from automotive_quality.api.authorization import Permission
from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.integrations.issue_tracker import LocalIssueTracker
from automotive_quality.shared.config import get_settings

EXPECTED_PERMISSIONS = {
    ("POST", "/api/v1/retrieval/search"): Permission.READ,
    ("POST", "/api/v1/baselines/ai/resolution"): Permission.OPERATE_AI,
    ("POST", "/api/v1/baselines/ai/rca"): Permission.OPERATE_AI,
    ("POST", "/api/v1/baselines/dq/rules/draft"): Permission.OPERATE_AI,
    ("GET", "/api/v1/test-runs"): Permission.READ,
    ("GET", "/api/v1/test-runs/{run_id}"): Permission.READ,
    ("GET", "/api/v1/metrics/overview"): Permission.READ,
    ("GET", "/api/v1/datasets"): Permission.READ,
    ("GET", "/api/v1/datasets/{version}"): Permission.READ,
    ("POST", "/api/v1/ai/requirements/analyze"): Permission.OPERATE_AI,
    ("POST", "/api/v1/ai/tests/generate"): Permission.OPERATE_AI,
    ("POST", "/api/v1/ai/dq-rules/generate"): Permission.OPERATE_AI,
    ("POST", "/api/v1/ai/rca/analyze"): Permission.OPERATE_AI,
    ("POST", "/api/v1/requirements/import/jira"): Permission.OPERATE_REQUIREMENTS,
    ("POST", "/api/v1/requirements/{requirement_version_id}/analyze"): Permission.OPERATE_REQUIREMENTS,
    ("POST", "/api/v1/requirements/{requirement_version_id}/generate-tests"): Permission.OPERATE_REQUIREMENTS,
    ("GET", "/api/v1/reviews/{review_id}"): Permission.READ,
    ("POST", "/api/v1/reviews/{review_id}/sync"): Permission.REVIEW,
    ("POST", "/api/v1/reviews/{review_id}/start"): Permission.REVIEW,
    ("POST", "/api/v1/reviews/{review_id}/assessment"): Permission.REVIEW,
    ("POST", "/api/v1/reviews/{review_id}/decision"): Permission.REVIEW,
    ("POST", "/api/v1/test-runs"): Permission.SUBMIT_TEST_RESULTS,
    ("GET", "/api/v1/traceability/requirements/{requirement_version_id}"): Permission.READ,
    ("GET", "/api/v1/ai-value/experiments"): Permission.READ,
    ("GET", "/api/v1/ai-operations/{operation_id}"): Permission.READ,
    ("POST", "/api/v1/external-sync/{link_id}/retry"): Permission.RETRY_EXTERNAL_SYNC,
}


@pytest.fixture
def authorization_database() -> Iterator:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

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
        yield engine
    finally:
        if previous is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous
        engine.dispose()


def _seed_review(
    engine,
    *,
    generated_by: str | None = "pytest-operator",
    missing_artifact: bool = False,
) -> tuple[str, str]:
    suffix = uuid4().hex[:12]
    requirement_id = f"REQV-AUTHZ-{suffix}"
    version_id = f"TCV-AUTHZ-{suffix}"
    review_id = f"REV-AUTHZ-{suffix}"
    with Session(engine) as session:
        session.add(models.RequirementVersion(
            requirement_version_id=requirement_id,
            requirement_id=f"REQ-AUTHZ-{suffix}",
            version=1,
            external_system="LOCAL",
            external_reference=f"AUTHZ-{suffix}",
            summary="Authorization fixture",
            description="Authorization fixture",
            acceptance_criteria="Authorization fixture",
            content_hash="a" * 64,
            created_by_principal_id="pytest-operator",
        ))
        if not missing_artifact:
            case_id = f"TC-AUTHZ-{suffix}"
            session.add(models.TestCase(
                test_case_id=case_id,
                suite=f"REQ-{suffix}",
                title="Authorization fixture",
                severity="P1",
                specification={"expected_result": "expected"},
                review_status="REVIEW_REQUIRED",
            ))
            session.add(models.TestCaseVersion(
                test_case_version_id=version_id,
                test_case_id=case_id,
                version=1,
                requirement_version_id=requirement_id,
                source_ai_run_id=None,
                generated_by_principal_id=generated_by,
                status="REVIEW_REQUIRED",
                content={"expected_result": "expected"},
            ))
        session.add(models.ReviewRequest(
            review_id=review_id,
            artifact_type="TEST_CASE_BATCH",
            artifact_ids=[version_id],
            status="REVIEW_REQUIRED",
            external_system="LOCAL",
        ))
        session.commit()
    return review_id, version_id


def test_every_v1_operation_has_exactly_one_explicit_permission_policy() -> None:
    actual: dict[tuple[str, str], Permission] = {}
    for route in v1.router.routes:
        assert isinstance(route, APIRoute)
        policies = [
            dependency.call.required_permission
            for dependency in route.dependant.dependencies
            if hasattr(dependency.call, "required_permission")
        ]
        assert len(policies) == 1, f"{route.path} must have exactly one permission policy"
        policy_index = next(
            index
            for index, dependency in enumerate(route.dependant.dependencies)
            if hasattr(dependency.call, "required_permission")
        )
        business_dependency_indexes = [
            index
            for index, dependency in enumerate(route.dependant.dependencies)
            if dependency.call in {database_session, v1.retrieval_service}
        ]
        assert all(policy_index < index for index in business_dependency_indexes)
        for method in route.methods:
            actual[(method, route.path)] = policies[0]
    assert actual == EXPECTED_PERMISSIONS


def test_reader_can_read_but_cannot_invoke_ai_or_mutations(authorization_database) -> None:
    del authorization_database
    with TestClient(app, headers=TEST_READER_HEADERS) as client:
        read = client.get("/api/v1/metrics/overview")
        ai = client.post("/api/v1/ai/requirements/analyze", json={"requirement": "must not run"})
        test_run = client.post("/api/v1/test-runs", json={})
        jira = client.post("/api/v1/requirements/import/jira", json={"issue_key": "NOPE-1"})
    assert read.status_code == 200
    assert ai.status_code == test_run.status_code == jira.status_code == 403


def test_operator_can_invoke_ai_but_cannot_review(authorization_database) -> None:
    review_id, _ = _seed_review(authorization_database)
    with TestClient(app, headers=TEST_AUTH_HEADERS) as client:
        ai = client.post(
            "/api/v1/ai/requirements/analyze",
            json={"requirement": "Resolved orders require timestamps"},
        )
        review = client.post(f"/api/v1/reviews/{review_id}/start")
    assert ai.status_code == 200
    assert review.status_code == 403


def test_reviewer_can_review_other_actor_output_but_cannot_invoke_ai(authorization_database) -> None:
    review_id, _ = _seed_review(authorization_database)
    with TestClient(app, headers=TEST_REVIEWER_HEADERS) as client:
        started = client.post(f"/api/v1/reviews/{review_id}/start")
        ai = client.post(
            "/api/v1/ai/requirements/analyze",
            json={"requirement": "must not run"},
        )
    assert started.status_code == 200
    assert ai.status_code == 403
    with Session(authorization_database) as session:
        review = session.get(models.ReviewRequest, review_id)
        assert review is not None and review.reviewer == "pytest-reviewer"


def test_forged_reviewer_identity_is_rejected_before_tracker_action(
    authorization_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_id, _ = _seed_review(authorization_database)
    calls = 0

    def forbidden_tracker():
        nonlocal calls
        calls += 1
        raise AssertionError("tracker must not be called")

    monkeypatch.setattr(v1, "_issue_tracker", forbidden_tracker)
    with TestClient(app, headers=TEST_REVIEWER_HEADERS) as client:
        response = client.post(
            f"/api/v1/reviews/{review_id}/decision",
            json={"status": "Approved", "reviewer": "forged-reviewer"},
        )
    assert response.status_code == 409
    assert calls == 0
    with Session(authorization_database) as session:
        review = session.get(models.ReviewRequest, review_id)
        assert review is not None and review.reviewer is None and review.status == "REVIEW_REQUIRED"


def test_self_review_is_denied_but_administrator_exception_is_explicit(authorization_database) -> None:
    denied_id, _ = _seed_review(authorization_database, generated_by="pytest-dual-role")
    admin_id, _ = _seed_review(authorization_database, generated_by="pytest-administrator")
    with TestClient(app, headers=TEST_DUAL_ROLE_HEADERS) as dual_client:
        denied = dual_client.post(f"/api/v1/reviews/{denied_id}/start")
    with TestClient(app, headers=TEST_ADMIN_HEADERS) as admin_client:
        allowed = admin_client.post(f"/api/v1/reviews/{admin_id}/start")
    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_invalid_review_relationship_fails_before_mutation(authorization_database) -> None:
    review_id, _ = _seed_review(authorization_database, missing_artifact=True)
    with TestClient(app, headers=TEST_REVIEWER_HEADERS) as client:
        response = client.post(f"/api/v1/reviews/{review_id}/start")
    assert response.status_code == 409
    with Session(authorization_database) as session:
        review = session.get(models.ReviewRequest, review_id)
        assert review is not None and review.reviewer is None and review.review_started_at is None


def test_review_sync_requires_a_valid_external_link_without_binding_actor(authorization_database) -> None:
    review_id, _ = _seed_review(authorization_database)
    with TestClient(app, headers=TEST_REVIEWER_HEADERS) as client:
        response = client.post(f"/api/v1/reviews/{review_id}/sync")
    assert response.status_code == 409
    with Session(authorization_database) as session:
        review = session.get(models.ReviewRequest, review_id)
        assert review is not None and review.reviewer is None and review.status == "REVIEW_REQUIRED"


def test_unauthorized_external_retry_and_submission_have_zero_side_effects(
    authorization_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del authorization_database
    calls = 0

    def forbidden_workflow(session):
        del session
        nonlocal calls
        calls += 1
        raise AssertionError("workflow must not be constructed")

    monkeypatch.setattr(v1, "_testing_workflow", forbidden_workflow)
    with TestClient(app, headers=TEST_READER_HEADERS) as client:
        retry = client.post("/api/v1/external-sync/1/retry")
        submission = client.post("/api/v1/test-runs", json={})
    assert retry.status_code == submission.status_code == 403
    assert calls == 0


def test_unknown_role_is_authenticated_but_has_no_permissions(
    authorization_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del authorization_database
    token = "test-only-unknown-role-token-with-no-production-value"
    config = json.dumps([{
        "principal_id": "pytest-unknown-role",
        "category": "test",
        "roles": ["unsupported-role"],
        "credentials": [{
            "key_id": "unknown-v1",
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        }],
    }])
    monkeypatch.setenv("API_AUTH_PRINCIPALS_JSON", config)
    get_settings.cache_clear()
    get_bearer_authenticator.cache_clear()
    try:
        with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
            forbidden = client.get("/api/v1/metrics/overview")
            unauthenticated = client.get("/api/v1/metrics/overview", headers={"Authorization": ""})
    finally:
        get_settings.cache_clear()
        get_bearer_authenticator.cache_clear()
    assert forbidden.status_code == 403
    assert unauthenticated.status_code == 401


def test_invalid_external_sync_relationship_is_rejected_without_tracker_call(
    authorization_database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(authorization_database) as session:
        link = models.ExternalIssueLink(
            provider="LOCAL",
            issue_key="BUG-MISSING",
            issue_url=None,
            artifact_type="TEST_RESULT",
            artifact_id="999999",
            idempotency_key=f"invalid:{uuid4().hex}",
            sync_status="FAILED",
            retry_count=1,
        )
        session.add(link)
        session.commit()
        link_id = link.link_id

    tracker = v1._issue_tracker()
    assert isinstance(tracker, LocalIssueTracker)
    monkeypatch.setattr(tracker, "create_defect", lambda **kwargs: pytest.fail(str(kwargs)))
    with TestClient(app, headers=TEST_AUTH_HEADERS) as client:
        response = client.post(f"/api/v1/external-sync/{link_id}/retry")
    assert response.status_code == 409
    with Session(authorization_database) as session:
        persisted = session.scalar(select(models.ExternalIssueLink).where(models.ExternalIssueLink.link_id == link_id))
        assert persisted is not None
        assert persisted.last_retry_by_principal_id is None
        assert persisted.retry_count == 1
