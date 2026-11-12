from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from conftest import TEST_AUTH_HEADERS, TEST_READER_HEADERS
from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from automotive_quality.api import v1
from automotive_quality.api.auth import AuthenticatedPrincipal
from automotive_quality.api.authorization import Permission
from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.api.rate_limits import (
    Admission,
    OperationCategory,
    enforce_rate_limit,
    ensure_ai_concurrency_protected,
    get_rate_limiter,
)
from automotive_quality.infrastructure.database.base import Base


@pytest.fixture(autouse=True)
def isolated_rate_limit_database() -> Iterator[None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def session_override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
            session.commit()

    previous = app.dependency_overrides.get(database_session)
    app.dependency_overrides[database_session] = session_override
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous
        engine.dispose()


class RecordingLease:
    def __init__(self) -> None:
        self.started = False
        self.released = False
        self.renewal_failed = False

    def start(self) -> None:
        self.started = True

    def release(self) -> None:
        self.released = True


class ControlledLimiter:
    def __init__(self, admissions: list[Admission] | None = None) -> None:
        self.admissions = admissions or [Admission(True, 1)]
        self.calls: list[tuple[str, OperationCategory]] = []
        self.leases: list[RecordingLease] = []

    def admit(self, principal_id: str, category: OperationCategory) -> Admission:
        self.calls.append((principal_id, category))
        return self.admissions[min(len(self.calls) - 1, len(self.admissions) - 1)]

    def acquire_ai_lease(self, principal_id: str) -> RecordingLease:
        assert principal_id == "pytest-operator"
        lease = RecordingLease()
        self.leases.append(lease)
        return lease


EXPECTED_CATEGORIES = {
    "/api/v1/retrieval/search": OperationCategory.READ,
    "/api/v1/baselines/ai/resolution": OperationCategory.AI,
    "/api/v1/baselines/ai/rca": OperationCategory.AI,
    "/api/v1/baselines/dq/rules/draft": OperationCategory.AI,
    "/api/v1/test-runs": {"GET": OperationCategory.READ, "POST": OperationCategory.MUTATION},
    "/api/v1/test-runs/{run_id}": OperationCategory.READ,
    "/api/v1/metrics/overview": OperationCategory.READ,
    "/api/v1/datasets": OperationCategory.READ,
    "/api/v1/datasets/{version}": OperationCategory.READ,
    "/api/v1/ai/requirements/analyze": OperationCategory.AI,
    "/api/v1/ai/tests/generate": OperationCategory.AI,
    "/api/v1/ai/dq-rules/generate": OperationCategory.AI,
    "/api/v1/ai/rca/analyze": OperationCategory.AI,
    "/api/v1/requirements/import/jira": OperationCategory.JIRA,
    "/api/v1/requirements/{requirement_version_id}/analyze": OperationCategory.AI,
    "/api/v1/requirements/{requirement_version_id}/generate-tests": OperationCategory.AI,
    "/api/v1/reviews/{review_id}": OperationCategory.READ,
    "/api/v1/reviews/{review_id}/sync": OperationCategory.JIRA,
    "/api/v1/reviews/{review_id}/start": OperationCategory.MUTATION,
    "/api/v1/reviews/{review_id}/assessment": OperationCategory.MUTATION,
    "/api/v1/reviews/{review_id}/decision": OperationCategory.MUTATION,
    "/api/v1/traceability/requirements/{requirement_version_id}": OperationCategory.READ,
    "/api/v1/ai-value/experiments": OperationCategory.READ,
    "/api/v1/external-sync/{link_id}/retry": OperationCategory.JIRA,
}


@contextmanager
def _override(limiter) -> Iterator[None]:
    previous = app.dependency_overrides.get(get_rate_limiter)
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_rate_limiter, None)
        else:
            app.dependency_overrides[get_rate_limiter] = previous


def test_every_protected_v1_route_has_exactly_one_documented_quota_category() -> None:
    actual: dict[str, OperationCategory | dict[str, OperationCategory]] = {}
    for route in v1.router.routes:
        assert isinstance(route, APIRoute)
        policies = [
            dependency.call.operation_category
            for dependency in route.dependant.dependencies
            if hasattr(dependency.call, "operation_category")
        ]
        assert len(policies) == 1
        category = policies[0]
        if route.path == "/api/v1/test-runs":
            existing = actual.setdefault(route.path, {})
            assert isinstance(existing, dict)
            for method in route.methods:
                existing[method] = category
        else:
            actual[route.path] = category
    assert actual == EXPECTED_CATEGORIES


def test_routes_in_same_category_share_principal_quota_and_return_retry_after() -> None:
    limiter = ControlledLimiter([Admission(True, 1), Admission(False, 17)])
    with _override(limiter), TestClient(app, headers=TEST_READER_HEADERS) as client:
        first = client.get("/api/v1/datasets")
        second = client.get("/api/v1/metrics/overview")
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"] == "17"
    assert second.json() == {"detail": "Request rate limit exceeded"}
    assert limiter.calls == [
        ("pytest-reader", OperationCategory.READ),
        ("pytest-reader", OperationCategory.READ),
    ]


def test_authenticated_identity_not_forged_headers_keys_quota() -> None:
    limiter = ControlledLimiter()
    forged = {**TEST_READER_HEADERS, "X-Principal-ID": "pytest-operator", "X-Role": "administrator"}
    with _override(limiter), TestClient(app, headers=forged) as client:
        assert client.get("/api/v1/datasets").status_code == 200
    assert limiter.calls == [("pytest-reader", OperationCategory.READ)]


def test_over_quota_rejection_precedes_database_ai_and_jira_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = ControlledLimiter([Admission(False, 9)])
    calls = {"database": 0, "ai": 0, "jira": 0}

    def forbidden_database():
        calls["database"] += 1
        raise AssertionError("database must not open")
        yield

    def forbidden(name: str):
        def fail(*args, **kwargs):
            del args, kwargs
            calls[name] += 1
            raise AssertionError(f"{name} must not execute")
        return fail

    previous_database = app.dependency_overrides.get(database_session)
    app.dependency_overrides[database_session] = forbidden_database
    monkeypatch.setattr(v1, "_ai_workflow", forbidden("ai"))
    monkeypatch.setattr(v1, "_issue_tracker", forbidden("jira"))
    try:
        with _override(limiter), TestClient(app, headers=TEST_AUTH_HEADERS) as client:
            responses = [
                client.post("/api/v1/ai/requirements/analyze", json={"requirement": "must not run"}),
                client.post("/api/v1/requirements/import/jira", json={"issue_key": "NOPE-1"}),
            ]
    finally:
        if previous_database is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous_database
    assert [response.status_code for response in responses] == [429, 429]
    assert calls == {"database": 0, "ai": 0, "jira": 0}


def test_ai_lease_released_after_success_and_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = ControlledLimiter()
    with _override(limiter), TestClient(app, headers=TEST_AUTH_HEADERS) as client:
        success = client.post(
            "/api/v1/ai/requirements/analyze",
            json={"requirement": "Resolved orders require timestamps"},
        )
        monkeypatch.setattr(v1, "_ai_workflow", lambda session: (_ for _ in ()).throw(RuntimeError("synthetic")))
        with pytest.raises(RuntimeError, match="synthetic"):
            client.post(
                "/api/v1/ai/requirements/analyze",
                json={"requirement": "Provider fails"},
            )
    assert success.status_code == 200
    assert len(limiter.leases) == 2
    assert all(lease.started and lease.released for lease in limiter.leases)


def test_ai_lease_released_when_dependency_is_cancelled() -> None:
    limiter = ControlledLimiter()
    principal = AuthenticatedPrincipal(
        principal_id="pytest-operator",
        category="test",
        roles=frozenset({"operator"}),
        key_id="test-key",
    )
    guard = enforce_rate_limit(Permission.OPERATE_AI, OperationCategory.AI, ai_concurrency=True)
    dependency = guard(principal, limiter)
    assert next(dependency).principal_id == principal.principal_id
    dependency.close()
    assert limiter.leases[0].started and limiter.leases[0].released


def test_lost_ai_lease_suppresses_success_and_releases_owned_token() -> None:
    limiter = ControlledLimiter()
    principal = AuthenticatedPrincipal(
        principal_id="pytest-operator",
        category="test",
        roles=frozenset({"operator"}),
        key_id="test-key",
    )
    guard = enforce_rate_limit(Permission.OPERATE_AI, OperationCategory.AI, ai_concurrency=True)
    dependency = guard(principal, limiter)
    admitted = next(dependency)
    assert admitted.principal_id == principal.principal_id
    limiter.leases[0].renewal_failed = True
    with pytest.raises(HTTPException) as lost:
        ensure_ai_concurrency_protected(admitted)
    assert lost.value.status_code == 503
    assert lost.value.detail == "AI concurrency protection was lost during execution"
    dependency.close()
    assert limiter.leases[0].released


def test_api_returns_503_instead_of_success_when_ai_lease_is_lost() -> None:
    limiter = ControlledLimiter()

    def lost_lease(principal_id: str) -> RecordingLease:
        assert principal_id == "pytest-operator"
        lease = RecordingLease()
        lease.renewal_failed = True
        limiter.leases.append(lease)
        return lease

    limiter.acquire_ai_lease = lost_lease  # type: ignore[method-assign]
    with _override(limiter), TestClient(app, headers=TEST_AUTH_HEADERS) as client:
        response = client.post(
            "/api/v1/ai/requirements/analyze",
            json={"requirement": "Resolved orders require timestamps"},
        )
    assert response.status_code == 503
    assert response.json() == {"detail": "AI concurrency protection was lost during execution"}
    assert limiter.leases[0].released


class OutageLimiter:
    def admit(self, principal_id, category):
        del principal_id, category
        raise RedisConnectionError("synthetic Redis outage with redis://secret@host")


def test_redis_outage_fails_closed_for_ai_but_reads_follow_documented_fail_open() -> None:
    limiter = OutageLimiter()
    with _override(limiter), TestClient(app) as client:
        ai = client.post(
            "/api/v1/ai/requirements/analyze",
            headers=TEST_AUTH_HEADERS,
            json={"requirement": "must not run"},
        )
        read = client.get("/api/v1/datasets", headers=TEST_READER_HEADERS)
    assert ai.status_code == 503
    assert ai.json() == {"detail": "Request admission control is temporarily unavailable"}
    assert "secret" not in ai.text
    assert read.status_code == 200


def test_unauthorized_request_never_reaches_quota() -> None:
    limiter = ControlledLimiter()
    with _override(limiter), TestClient(app, headers=TEST_READER_HEADERS) as client:
        response = client.post(
            "/api/v1/ai/requirements/analyze",
            json={"requirement": "must not run"},
        )
    assert response.status_code == 403
    assert limiter.calls == []
