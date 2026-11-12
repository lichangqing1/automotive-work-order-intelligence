from __future__ import annotations

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from uuid import uuid4

import pytest
from conftest import TEST_AUTH_HEADERS
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from automotive_quality.api import v1
from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.api.rate_limits import RedisRateLimiter, get_rate_limiter
from automotive_quality.application.ai_testing_workflow import AITestingWorkflow
from automotive_quality.domains.ai.schemas import GeneratedTestSuite, RequirementAnalysis
from automotive_quality.domains.ai.workflows import AIWorkflowService
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.repositories import AIRunRepository
from automotive_quality.integrations.issue_tracker import LocalIssueTracker
from automotive_quality.shared.config import Settings


def _engine():
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL integration database is not configured")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        if connection.exec_driver_sql("select current_database()").scalar_one() != "automotive_verify":
            pytest.fail("AI operation integration tests require automotive_verify")
    return engine


def _override_database(engine) -> Iterator[Session]:
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


class BlockingAnalysisWorkflow:
    def __init__(self) -> None:
        self.calls = 0
        self.last_run_id: str | None = None
        self.entered = Event()
        self.release = Event()
        self.lock = Lock()

    def analyze_requirement(self, requirement: str) -> RequirementAnalysis:
        with self.lock:
            self.calls += 1
            call = self.calls
        self.last_run_id = f"AIR-PG-{call}"
        self.entered.set()
        assert self.release.wait(timeout=5)
        return RequirementAnalysis(
            business_rules=[requirement], risks=[], boundary_conditions=[],
            missing_information=[], recommended_test_scenarios=[],
        )


@pytest.mark.postgres
def test_postgres_concurrent_duplicate_executes_provider_once_and_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    workflow = BlockingAnalysisWorkflow()
    monkeypatch.setattr(v1, "_ai_workflow", lambda session: workflow)
    previous = app.dependency_overrides.get(database_session)

    def session_override():
        yield from _override_database(engine)

    app.dependency_overrides[database_session] = session_override
    key = f"pg-analysis-{uuid4().hex}"
    headers = {**TEST_AUTH_HEADERS, "Idempotency-Key": key}

    def request():
        with TestClient(app) as client:
            return client.post(
                "/api/v1/ai/requirements/analyze",
                headers=headers,
                json={"requirement": "Resolved orders require timestamps"},
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(request)
            assert workflow.entered.wait(timeout=5)
            duplicate = request()
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"]["code"] == "OPERATION_IN_PROGRESS"
            workflow.release.set()
            first = first_future.result(timeout=5)
        replay = request()
    finally:
        if previous is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous

    assert first.status_code == replay.status_code == 200
    assert replay.headers["Idempotent-Replay"] == "true"
    assert workflow.calls == 1
    with Session(engine) as verify:
        operations = verify.scalars(select(models.AIOperation).where(
            models.AIOperation.idempotency_key == key
        )).all()
        assert len(operations) == 1 and operations[0].state == "SUCCEEDED"
    engine.dispose()


@pytest.mark.postgres
@pytest.mark.redis
def test_real_redis_lease_loss_marks_postgres_operation_ambiguous_and_blocks_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_url = os.getenv("REDIS_TEST_URL")
    if not redis_url:
        pytest.skip("REDIS_TEST_URL is not configured")
    engine = _engine()
    workflow = BlockingAnalysisWorkflow()
    monkeypatch.setattr(v1, "_ai_workflow", lambda session: workflow)
    namespace = f"automotive-quality-ai-operation-test:{uuid4().hex}"
    redis_client = Redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
    limiter = RedisRateLimiter(redis_client, Settings(
        redis_url=redis_url,
        rate_limit_namespace=namespace,
        ai_concurrency_lease_seconds=1,
    ))
    previous_database = app.dependency_overrides.get(database_session)
    previous_limiter = app.dependency_overrides.get(get_rate_limiter)

    def session_override():
        yield from _override_database(engine)

    app.dependency_overrides[database_session] = session_override
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    key = f"redis-loss-{uuid4().hex}"
    headers = {**TEST_AUTH_HEADERS, "Idempotency-Key": key}

    def request():
        with TestClient(app) as client:
            return client.post(
                "/api/v1/ai/requirements/analyze",
                headers=headers,
                json={"requirement": "Resolved orders require timestamps"},
            )

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(request)
            assert workflow.entered.wait(timeout=5)
            lease_keys = list(redis_client.scan_iter(match=f"{namespace}:concurrency:ai:*"))
            assert len(lease_keys) == 1
            redis_client.delete(lease_keys[0])
            assert workflow.release.wait(timeout=0.6) is False
            workflow.release.set()
            first = future.result(timeout=5)
        retry = request()
    finally:
        keys = list(redis_client.scan_iter(match=f"{namespace}:*"))
        if keys:
            redis_client.delete(*keys)
        redis_client.close()
        if previous_database is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous_database
        if previous_limiter is None:
            app.dependency_overrides.pop(get_rate_limiter, None)
        else:
            app.dependency_overrides[get_rate_limiter] = previous_limiter

    assert first.status_code == 503
    operation_id = first.json()["detail"]["operation_id"]
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "OPERATION_AMBIGUOUS"
    assert workflow.calls == 1
    with Session(engine) as verify:
        operation = verify.get(models.AIOperation, operation_id)
        assert operation is not None and operation.state == "AMBIGUOUS"
    engine.dispose()


class CountingSuiteProvider:
    name = "POSTGRES_FIXTURE"
    model = "deterministic"

    def __init__(self) -> None:
        self.calls = 0

    def generate_structured(self, prompt: str, response_model):
        del prompt
        self.calls += 1
        assert response_model is GeneratedTestSuite
        return response_model.model_validate({
            "requirement": "Synthetic persisted requirement",
            "cases": [{
                "test_id": "PG-IDEMPOTENT-1",
                "title": "Persist one review batch",
                "objective": "Verify operation idempotency",
                "preconditions": [],
                "test_data": [],
                "steps": ["Submit deterministic fixture"],
                "expected_result": "One review batch exists",
                "category": "positive",
                "priority": "P1",
            }],
        })


@pytest.mark.postgres
def test_completed_persisted_generation_replays_without_duplicate_review_or_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    suffix = uuid4().hex[:12]
    requirement_id = f"REQV-IDEM-{suffix}"
    with Session(engine) as setup:
        setup.add(models.RequirementVersion(
            requirement_version_id=requirement_id,
            requirement_id=f"REQ-IDEM-{suffix}",
            version=1,
            external_system="LOCAL",
            external_reference=f"IDEM-{suffix}",
            summary="Persisted idempotency fixture",
            description="Persisted idempotency fixture",
            acceptance_criteria="Persisted idempotency fixture",
            content_hash="i" * 64,
            analysis={
                "business_rules": ["Persist one review batch"],
                "risks": [], "boundary_conditions": [], "missing_information": [],
                "recommended_test_scenarios": [],
            },
        ))
        setup.commit()

    provider = CountingSuiteProvider()
    tracker = LocalIssueTracker()

    def workflow(session: Session) -> AITestingWorkflow:
        return AITestingWorkflow(
            session,
            AIWorkflowService(provider, AIRunRepository(session)),
            tracker,
            {"Approved"},
            {"Rejected"},
        )

    monkeypatch.setattr(v1, "_testing_workflow", workflow)
    previous = app.dependency_overrides.get(database_session)

    def session_override():
        yield from _override_database(engine)

    app.dependency_overrides[database_session] = session_override
    key = f"pg-generation-{uuid4().hex}"
    headers = {**TEST_AUTH_HEADERS, "Idempotency-Key": key}
    try:
        with TestClient(app) as client:
            first = client.post(
                f"/api/v1/requirements/{requirement_id}/generate-tests", headers=headers
            )
            replay = client.post(
                f"/api/v1/requirements/{requirement_id}/generate-tests", headers=headers
            )
    finally:
        if previous is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert replay.headers["Idempotent-Replay"] == "true"
    assert provider.calls == 1
    with Session(engine) as verify:
        operation = verify.scalar(select(models.AIOperation).where(
            models.AIOperation.idempotency_key == key
        ))
        assert operation is not None and operation.state == "SUCCEEDED"
        assert verify.scalar(select(func.count()).select_from(models.ReviewRequest).where(
            models.ReviewRequest.ai_operation_id == operation.operation_id
        )) == 1
        assert verify.scalar(select(func.count()).select_from(models.ExternalIssueLink).where(
            models.ExternalIssueLink.idempotency_key == f"review:{operation.operation_id}"
        )) == 1
    engine.dispose()
