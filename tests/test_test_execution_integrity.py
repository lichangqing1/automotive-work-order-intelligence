from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.application.ai_testing_workflow import AITestingWorkflow, WorkflowConflict
from automotive_quality.domains.ai.providers.mock import MockProvider
from automotive_quality.domains.ai.schemas import AIRootCauseAnalysis
from automotive_quality.domains.ai.workflows import AIWorkflowService
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.database.repositories import AIRunRepository
from automotive_quality.integrations.issue_tracker import LocalIssueTracker


@pytest.fixture
def execution_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(models.Dataset(dataset_id="DS-EXEC", name="execution-fixture", source_type="synthetic"))
        session.add(
            models.DatasetVersion(
                dataset_version_id="DSV-EXEC-V1",
                dataset_id="DS-EXEC",
                version="exec-v1",
                row_count=1,
                content_hash="fixture-hash",
            )
        )
        session.add(
            models.RequirementVersion(
                requirement_version_id="REQV-EXEC",
                requirement_id="REQ-EXEC",
                version=1,
                external_system="local",
                external_reference="EXEC-1",
                summary="Validate submitted results",
                description="Approved tests require genuine submitted results.",
                acceptance_criteria="Every requested test has one submitted result.",
                content_hash="requirement-hash",
            )
        )
        cases = [
            ("TC-ONE", "TCV-ONE", "APPROVED", "expected one"),
            ("TC-TWO", "TCV-TWO", "APPROVED", "expected two"),
            ("TC-PENDING", "TCV-PENDING", "REVIEW_REQUIRED", "expected pending"),
            ("TC-REJECTED", "TCV-REJECTED", "REJECTED", "expected rejected"),
        ]
        for case_id, version_id, status, expected in cases:
            session.add(
                models.TestCase(
                    test_case_id=case_id,
                    suite="REQ-EXEC",
                    title=case_id,
                    severity="P1",
                    specification={"expected_result": expected},
                    review_status=status,
                )
            )
            session.add(
                models.TestCaseVersion(
                    test_case_version_id=version_id,
                    test_case_id=case_id,
                    version=1,
                    requirement_version_id="REQV-EXEC",
                    status=status,
                    content={"expected_result": expected},
                )
            )
        session.commit()
    yield engine
    engine.dispose()


@pytest.fixture
def execution_session(execution_engine) -> Iterator[Session]:
    with Session(execution_engine) as session:
        yield session


@pytest.fixture
def workflow(execution_session: Session) -> AITestingWorkflow:
    provider = MockProvider(
        {
            AIRootCauseAnalysis: {
                "failure_class": "INSUFFICIENT_EVIDENCE",
                "probable_root_causes": [],
                "supporting_evidence": [],
                "recommended_checks": ["Inspect submitted execution evidence"],
                "confidence": 0.1,
                "insufficient_evidence": True,
            }
        }
    )
    ai = AIWorkflowService(provider, AIRunRepository(execution_session))
    return AITestingWorkflow(execution_session, ai, LocalIssueTracker(), {"Approved"}, {"Rejected"})


def _run_count(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(models.TestRun)) or 0)


def test_empty_actual_results_are_rejected_without_persistence(
    workflow: AITestingWorkflow, execution_session: Session
) -> None:
    with pytest.raises(WorkflowConflict, match="Actual results"):
        workflow.execute("REQV-EXEC", ["TCV-ONE"], {}, "exec-v1")
    assert _run_count(execution_session) == 0


def test_partial_actual_results_are_rejected_without_persistence(
    workflow: AITestingWorkflow, execution_session: Session
) -> None:
    with pytest.raises(WorkflowConflict, match="exactly match"):
        workflow.execute(
            "REQV-EXEC",
            ["TCV-ONE", "TCV-TWO"],
            {"TCV-ONE": "expected one"},
            "exec-v1",
        )
    assert _run_count(execution_session) == 0


def test_unexpected_actual_result_keys_are_rejected(
    workflow: AITestingWorkflow, execution_session: Session
) -> None:
    with pytest.raises(WorkflowConflict, match="exactly match"):
        workflow.execute(
            "REQV-EXEC",
            ["TCV-ONE"],
            {"TCV-ONE": "expected one", "TCV-UNKNOWN": "unexpected"},
            "exec-v1",
        )
    assert _run_count(execution_session) == 0


def test_nonexistent_dataset_version_is_rejected(
    workflow: AITestingWorkflow, execution_session: Session
) -> None:
    with pytest.raises(WorkflowConflict, match="dataset version"):
        workflow.execute("REQV-EXEC", ["TCV-ONE"], {"TCV-ONE": "expected one"}, "missing-v1")
    assert _run_count(execution_session) == 0


def test_unknown_test_case_version_is_rejected(
    workflow: AITestingWorkflow, execution_session: Session
) -> None:
    with pytest.raises(WorkflowConflict, match="Unknown test-case version"):
        workflow.execute(
            "REQV-EXEC",
            ["TCV-UNKNOWN"],
            {"TCV-UNKNOWN": "submitted value"},
            "exec-v1",
        )
    assert _run_count(execution_session) == 0


@pytest.mark.parametrize("version_id", ["TCV-PENDING", "TCV-REJECTED"])
def test_unapproved_test_case_versions_remain_non_executable(
    workflow: AITestingWorkflow,
    execution_session: Session,
    version_id: str,
) -> None:
    with pytest.raises(WorkflowConflict, match="Only APPROVED"):
        workflow.execute("REQV-EXEC", [version_id], {version_id: "submitted value"}, "exec-v1")
    assert _run_count(execution_session) == 0


def test_complete_matching_submitted_results_pass_and_preserve_provenance(
    workflow: AITestingWorkflow, execution_session: Session
) -> None:
    response = workflow.execute(
        "REQV-EXEC",
        ["TCV-ONE", "TCV-TWO"],
        {"TCV-ONE": "expected one", "TCV-TWO": "expected two"},
        "exec-v1",
    )

    assert response == {
        "test_run_id": response["test_run_id"],
        "status": "PASSED",
        "execution_mode": "SUBMITTED_RESULTS_VALIDATION",
        "automatically_executed": False,
        "submitted_results": 2,
        "passed": 2,
        "failed": 0,
        "total": 2,
        "external_sync": [],
    }
    results = execution_session.scalars(
        select(models.TestResult).where(models.TestResult.test_run_id == response["test_run_id"])
    ).all()
    assert {item.actual for item in results} == {"expected one", "expected two"}
    assert all(item.evidence["result_source"] == "CALLER_SUBMITTED" for item in results)
    assert all(item.evidence["dataset_version_id"] == "DSV-EXEC-V1" for item in results)


def test_complete_nonmatching_submitted_result_fails(
    workflow: AITestingWorkflow, execution_session: Session
) -> None:
    response = workflow.execute(
        "REQV-EXEC",
        ["TCV-ONE"],
        {"TCV-ONE": "observed failure"},
        "exec-v1",
    )

    assert response["status"] == "FAILED"
    assert response["passed"] == 0
    assert response["failed"] == 1
    result = execution_session.scalar(
        select(models.TestResult).where(models.TestResult.test_run_id == response["test_run_id"])
    )
    assert result is not None
    assert result.status == "FAILED"
    assert result.actual == "observed failure"


def test_invalid_rca_output_is_blocked_before_external_issue_sync(
    execution_session: Session,
) -> None:
    provider = MockProvider({
        AIRootCauseAnalysis: {
            "failure_class": "TEST_FAILURE",
            "probable_root_causes": ["submitted_result_mismatch"],
            "supporting_evidence": ["EV-FABRICATED"],
            "recommended_checks": ["Inspect submitted evidence"],
            "confidence": 0.8,
            "insufficient_evidence": False,
            "claims": [{
                "claim": "submitted_result_mismatch",
                "evidence_ids": ["EV-FABRICATED"],
            }],
        },
    })
    tracker = LocalIssueTracker()
    workflow = AITestingWorkflow(
        execution_session,
        AIWorkflowService(provider, AIRunRepository(execution_session)),
        tracker,
        {"Approved"},
        {"Rejected"},
    )

    response = workflow.execute(
        "REQV-EXEC",
        ["TCV-ONE"],
        {"TCV-ONE": "observed failure"},
        "exec-v1",
    )

    assert response["status"] == "FAILED"
    assert response["external_sync"] == ["FAILED"]
    assert not [key for key in tracker.issues if key.startswith("BUG-")]
    result = execution_session.scalar(
        select(models.TestResult).where(models.TestResult.test_run_id == response["test_run_id"])
    )
    assert result is not None
    assert result.rca_ai_run_id is None
    successful_rca_runs = execution_session.scalars(
        select(models.AIRun).where(
            models.AIRun.task_type == "rca",
            models.AIRun.status == "SUCCEEDED",
        )
    ).all()
    assert successful_rca_runs == []


def test_valid_rca_output_keeps_audit_and_external_traceability(
    execution_session: Session,
) -> None:
    provider = MockProvider({
        AIRootCauseAnalysis: {
            "failure_class": "TEST_FAILURE",
            "probable_root_causes": ["submitted_result_mismatch"],
            "supporting_evidence": ["EV-ACTUAL"],
            "recommended_checks": ["Inspect submitted evidence"],
            "confidence": 0.8,
            "insufficient_evidence": False,
            "claims": [{
                "claim": "submitted_result_mismatch",
                "evidence_ids": ["EV-ACTUAL"],
            }],
        },
    })
    tracker = LocalIssueTracker()
    workflow = AITestingWorkflow(
        execution_session,
        AIWorkflowService(provider, AIRunRepository(execution_session)),
        tracker,
        {"Approved"},
        {"Rejected"},
    )

    response = workflow.execute(
        "REQV-EXEC",
        ["TCV-ONE"],
        {"TCV-ONE": "observed failure"},
        "exec-v1",
    )

    assert response["external_sync"] == ["SUCCEEDED"]
    bug_key = next(key for key in tracker.issues if key.startswith("BUG-"))
    comments = tracker.issues[bug_key]["comments"]
    assert isinstance(comments, list)
    assert "\"evidence_reference_status\": \"VALIDATED\"" in comments[0]
    assert "\"review_status\": \"REVIEW_REQUIRED\"" in comments[0]
    result = execution_session.scalar(
        select(models.TestResult).where(models.TestResult.test_run_id == response["test_run_id"])
    )
    assert result is not None
    ai_run = execution_session.get(models.AIRun, result.rca_ai_run_id)
    assert ai_run is not None
    assert ai_run.status == "SUCCEEDED"
    assert ai_run.output["evidence_reference_status"] == "VALIDATED"


def test_transaction_failure_rolls_back_run_and_results(
    workflow: AITestingWorkflow,
    execution_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_flush = execution_session.flush

    def fail_while_persisting_results(*args, **kwargs) -> None:
        if any(isinstance(item, models.TestResult) for item in execution_session.new):
            raise SQLAlchemyError("simulated persistence failure")
        original_flush(*args, **kwargs)

    monkeypatch.setattr(execution_session, "flush", fail_while_persisting_results)
    with pytest.raises(SQLAlchemyError, match="simulated persistence failure"):
        workflow.execute("REQV-EXEC", ["TCV-ONE"], {"TCV-ONE": "expected one"}, "exec-v1")

    assert _run_count(execution_session) == 0
    assert execution_session.scalar(select(func.count()).select_from(models.TestResult)) == 0


def test_test_run_api_returns_consistent_validation_and_provenance(
    execution_engine,
) -> None:
    previous_override = app.dependency_overrides.get(database_session)

    def _session_override() -> Iterator[Session]:
        with Session(execution_engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[database_session] = _session_override
    try:
        with TestClient(app) as client:
            invalid = client.post(
                "/api/v1/test-runs",
                json={
                    "requirement_version_id": "REQV-EXEC",
                    "test_case_version_ids": ["TCV-ONE"],
                    "dataset_version": "exec-v1",
                    "actuals": {},
                },
            )
            valid = client.post(
                "/api/v1/test-runs",
                json={
                    "requirement_version_id": "REQV-EXEC",
                    "test_case_version_ids": ["TCV-ONE"],
                    "dataset_version": "exec-v1",
                    "actuals": {"TCV-ONE": "expected one"},
                },
            )
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous_override

    assert invalid.status_code == 409
    assert invalid.json() == {"detail": "Actual results are required for every requested test-case version"}
    assert valid.status_code == 200
    assert valid.json()["execution_mode"] == "SUBMITTED_RESULTS_VALIDATION"
    assert valid.json()["automatically_executed"] is False
