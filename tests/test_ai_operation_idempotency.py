from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import TEST_ADMIN_HEADERS, TEST_AUTH_HEADERS, TEST_READER_HEADERS
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from automotive_quality.api import v1
from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.api.rate_limits import Admission, get_rate_limiter
from automotive_quality.application.ai_operations import (
    AIOperationConflict,
    AIOperationState,
    AIOperationStore,
    OperationClaim,
    canonical_request_hash,
)
from automotive_quality.domains.ai.schemas import RequirementAnalysis
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.shared.config import Settings


class CountingWorkflow:
    def __init__(self) -> None:
        self.calls = 0
        self.last_run_id: str | None = None

    def analyze_requirement(self, requirement: str) -> RequirementAnalysis:
        self.calls += 1
        self.last_run_id = f"AIR-COUNT-{self.calls}"
        return RequirementAnalysis(
            business_rules=[requirement],
            risks=[],
            boundary_conditions=[],
            missing_information=[],
            recommended_test_scenarios=[],
        )


class TimeoutWorkflow(CountingWorkflow):
    def analyze_requirement(self, requirement: str) -> RequirementAnalysis:
        del requirement
        self.calls += 1
        self.last_run_id = "AIR-TIMEOUT-1"
        raise TimeoutError("synthetic provider timeout containing token=must-not-leak")


class _Lease:
    def __init__(self, lost: bool = False) -> None:
        self.renewal_failed = lost

    def start(self) -> None:
        return None

    def release(self) -> None:
        return None


class _Limiter:
    def __init__(self, *, lost: bool = False) -> None:
        self.lost = lost

    def admit(self, principal_id, category) -> Admission:
        del principal_id, category
        return Admission(True, 1)

    def acquire_ai_lease(self, principal_id) -> _Lease:
        del principal_id
        return _Lease(self.lost)


@pytest.fixture
def operation_database(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'operations.db'}")
    Base.metadata.create_all(engine)

    def session_override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
            session.commit()

    previous = app.dependency_overrides.get(database_session)
    app.dependency_overrides[database_session] = session_override
    try:
        with Session(engine) as inspection:
            yield inspection
    finally:
        if previous is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous
        engine.dispose()


def test_completed_request_replays_without_provider_invocation(
    operation_database: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = CountingWorkflow()
    monkeypatch.setattr(v1, "_ai_workflow", lambda session: workflow)
    headers = {**TEST_AUTH_HEADERS, "Idempotency-Key": "analysis-replay-0001"}
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/ai/requirements/analyze",
            headers=headers,
            json={"requirement": "Resolved orders require timestamps"},
        )
        replay = client.post(
            "/api/v1/ai/requirements/analyze",
            headers=headers,
            json={"requirement": "Resolved orders require timestamps"},
        )
    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert replay.headers["Idempotent-Replay"] == "true"
    assert replay.headers["X-AI-Operation-ID"] == first.headers["X-AI-Operation-ID"]
    assert workflow.calls == 1
    operation_database.expire_all()
    operations = operation_database.scalars(select(models.AIOperation)).all()
    assert len(operations) == 1 and operations[0].state == "SUCCEEDED"


def test_same_key_conflicting_payload_is_rejected_and_principals_are_isolated(
    operation_database: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del operation_database
    workflow = CountingWorkflow()
    monkeypatch.setattr(v1, "_ai_workflow", lambda session: workflow)
    key = "analysis-scope-0001"
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/ai/requirements/analyze",
            headers={**TEST_AUTH_HEADERS, "Idempotency-Key": key},
            json={"requirement": "Resolved orders require timestamps"},
        )
        conflict = client.post(
            "/api/v1/ai/requirements/analyze",
            headers={**TEST_AUTH_HEADERS, "Idempotency-Key": key},
            json={"requirement": "Closed orders require evidence"},
        )
        independent = client.post(
            "/api/v1/ai/requirements/analyze",
            headers={**TEST_ADMIN_HEADERS, "Idempotency-Key": key},
            json={"requirement": "Closed orders require evidence"},
        )
    assert first.status_code == independent.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert workflow.calls == 2


def test_different_keys_are_independent_and_shared_deployment_requires_a_key(
    operation_database: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del operation_database
    workflow = CountingWorkflow()
    monkeypatch.setattr(v1, "_ai_workflow", lambda session: workflow)
    with TestClient(app) as client:
        for key in ("analysis-independent-0001", "analysis-independent-0002"):
            assert client.post(
                "/api/v1/ai/requirements/analyze",
                headers={**TEST_AUTH_HEADERS, "Idempotency-Key": key},
                json={"requirement": "Resolved orders require timestamps"},
            ).status_code == 200
    assert workflow.calls == 2

    production = Settings(
        environment="production",
        api_auth_principals_json="[]",
        api_trusted_hosts="api.internal.example",
        api_docs_enabled=False,
        rate_limit_read_fail_open=False,
    )
    monkeypatch.setattr(v1, "get_settings", lambda: production)
    with TestClient(app) as client:
        missing = client.post(
            "/api/v1/ai/requirements/analyze",
            headers=TEST_AUTH_HEADERS,
            json={"requirement": "Resolved orders require timestamps"},
        )
    assert missing.status_code == 428
    assert missing.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert workflow.calls == 2


def test_running_operation_is_not_taken_over_and_stale_owner_cannot_complete(
    operation_database: Session,
) -> None:
    store = AIOperationStore(operation_database)
    values = {
        "principal_id": "pytest-operator",
        "operation_type": "REQUIREMENT_ANALYSIS",
        "target_resource": "direct",
        "idempotency_key": "running-operation-0001",
        "request_hash": canonical_request_hash({"requirement": "fixture"}),
    }
    owner = store.claim(**values)
    duplicate = store.claim(**values)
    assert owner.is_owner and not duplicate.is_owner
    assert duplicate.state is AIOperationState.RUNNING

    stale = OperationClaim(owner.operation_id, "stale-owner-token", AIOperationState.RUNNING)
    with pytest.raises(AIOperationConflict, match="ownership was lost"):
        store.succeed(stale, {"result": "stale"}, ai_run_id=None)
    store.succeed(owner, {"result": "owner"}, ai_run_id=None)
    replay = store.claim(**values)
    assert replay.state is AIOperationState.SUCCEEDED
    assert replay.response_payload == {"result": "owner"}


def test_operation_state_survives_business_transaction_rollback(
    operation_database: Session,
) -> None:
    store = AIOperationStore(operation_database)
    claim = store.claim(
        principal_id="pytest-operator",
        operation_type="TEST_GENERATION",
        target_resource="REQV-ROLLBACK",
        idempotency_key="rollback-operation-0001",
        request_hash=canonical_request_hash({"requirement_version_id": "REQV-ROLLBACK"}),
    )
    operation_database.add(models.RequirementVersion(
        requirement_version_id="REQV-ROLLBACK",
        requirement_id="REQ-ROLLBACK",
        version=1,
        external_system="LOCAL",
        external_reference="ROLLBACK-1",
        summary="Rolled back fixture",
        description="Rolled back fixture",
        content_hash="r" * 64,
    ))
    operation_database.flush()
    operation_database.rollback()
    store.fail(claim, "BUSINESS_TRANSACTION_ROLLED_BACK", ambiguous=True)

    operation_database.expire_all()
    assert operation_database.get(models.RequirementVersion, "REQV-ROLLBACK") is None
    operation = operation_database.get(models.AIOperation, claim.operation_id)
    assert operation is not None and operation.state == "AMBIGUOUS"


def test_lost_lease_marks_operation_ambiguous_and_blocks_retry_and_cross_principal_status(
    operation_database: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del operation_database
    workflow = CountingWorkflow()
    monkeypatch.setattr(v1, "_ai_workflow", lambda session: workflow)
    previous = app.dependency_overrides.get(get_rate_limiter)
    app.dependency_overrides[get_rate_limiter] = lambda: _Limiter(lost=True)
    headers = {**TEST_AUTH_HEADERS, "Idempotency-Key": "analysis-ambiguous-0001"}
    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/v1/ai/requirements/analyze",
                headers=headers,
                json={"requirement": "Resolved orders require timestamps"},
            )
            operation_id = first.json()["detail"]["operation_id"]
            retry = client.post(
                "/api/v1/ai/requirements/analyze",
                headers=headers,
                json={"requirement": "Resolved orders require timestamps"},
            )
            own_status = client.get(f"/api/v1/ai-operations/{operation_id}", headers=TEST_AUTH_HEADERS)
            other_status = client.get(f"/api/v1/ai-operations/{operation_id}", headers=TEST_READER_HEADERS)
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_rate_limiter, None)
        else:
            app.dependency_overrides[get_rate_limiter] = previous
    assert first.status_code == 503
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "OPERATION_AMBIGUOUS"
    assert own_status.json()["state"] == "AMBIGUOUS"
    assert own_status.json()["recovery"] == "MANUAL_RECONCILIATION_REQUIRED"
    assert other_status.status_code == 404
    assert workflow.calls == 1


def test_provider_timeout_returns_sanitized_ambiguous_recovery_response(
    operation_database: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del operation_database
    workflow = TimeoutWorkflow()
    monkeypatch.setattr(v1, "_ai_workflow", lambda session: workflow)
    headers = {**TEST_AUTH_HEADERS, "Idempotency-Key": "analysis-timeout-0001"}
    with TestClient(app) as client:
        first = client.post(
            "/api/v1/ai/requirements/analyze",
            headers=headers,
            json={"requirement": "Resolved orders require timestamps"},
        )
        retry = client.post(
            "/api/v1/ai/requirements/analyze",
            headers=headers,
            json={"requirement": "Resolved orders require timestamps"},
        )
    assert first.status_code == 503
    assert first.json()["detail"]["code"] == "OPERATION_AMBIGUOUS"
    assert "must-not-leak" not in first.text
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "OPERATION_AMBIGUOUS"
    assert workflow.calls == 1
