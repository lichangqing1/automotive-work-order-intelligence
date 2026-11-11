from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from automotive_quality.application.ai_testing_workflow import AITestingWorkflow, WorkflowConflict
from automotive_quality.domains.ai.providers.mock import MockProvider
from automotive_quality.domains.ai.schemas import AIRootCauseAnalysis, GeneratedTestSuite
from automotive_quality.domains.ai.workflows import AIWorkflowService
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.database.repositories import AIRunRepository
from automotive_quality.integrations.issue_tracker import LocalIssueTracker

ANALYSIS = {
    "business_rules": ["Generated tests remain requirement-scoped"],
    "risks": ["Cross-requirement identity collision"],
    "boundary_conditions": [],
    "missing_information": [],
    "recommended_test_scenarios": ["Generate the same display ID twice"],
}


def _case(test_id: str = "AI-TC-001", title: str = "Validate requirement behavior") -> dict[str, object]:
    return {
        "test_id": test_id,
        "title": title,
        "objective": "Preserve requirement identity",
        "preconditions": [],
        "test_data": [],
        "steps": ["Submit the requirement fixture"],
        "expected_result": "The correct requirement behavior is retained",
        "category": "positive",
        "priority": "P1",
    }


def _suite(*cases: dict[str, object]) -> dict[str, object]:
    return {"requirement": "Synthetic identity fixture", "cases": list(cases or (_case(),))}


def _seed(session: Session) -> None:
    session.add_all([
        models.RequirementVersion(
            requirement_version_id=f"REQV-{suffix}", requirement_id=f"REQ-{suffix}", version=1,
            external_system="LOCAL", external_reference=suffix, summary=f"Requirement {suffix}",
            description=f"Requirement {suffix} behavior", acceptance_criteria=suffix,
            content_hash=f"hash-{suffix.lower()}", analysis=ANALYSIS,
        )
        for suffix in ("A", "B")
    ])
    session.add(models.Dataset(dataset_id="DS-IDENTITY", name="identity-fixture", source_type="synthetic"))
    session.add(models.DatasetVersion(
        dataset_version_id="DSV-IDENTITY-V1", dataset_id="DS-IDENTITY", version="identity-v1",
        row_count=1, content_hash="identity-hash",
    ))
    session.commit()


def _engine(url: str = "sqlite+pysqlite:///:memory:"):
    kwargs = {"connect_args": {"check_same_thread": False}}
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
    with Session(engine) as session:
        _seed(session)
    return engine


@pytest.fixture
def identity_engine():
    engine = _engine()
    yield engine
    engine.dispose()


@pytest.fixture
def identity_session(identity_engine):
    with Session(identity_engine) as session:
        yield session


def _workflow(session: Session, tracker=None, suite=None) -> AITestingWorkflow:
    provider = MockProvider({
        GeneratedTestSuite: suite or _suite(),
        AIRootCauseAnalysis: {
            "failure_class": "TEST_FAILURE",
            "probable_root_causes": ["submitted_result_mismatch"],
            "supporting_evidence": ["EV-ACTUAL"],
            "recommended_checks": ["Inspect submitted evidence"],
            "confidence": 0.8,
            "insufficient_evidence": False,
            "claims": [{"claim": "submitted_result_mismatch", "evidence_ids": ["EV-ACTUAL"]}],
        },
    })
    return AITestingWorkflow(
        session, AIWorkflowService(provider, AIRunRepository(session)),
        tracker or LocalIssueTracker(), {"Approved"}, {"Rejected"},
    )


def _version(session: Session, generated: dict[str, object]) -> models.TestCaseVersion:
    ids = generated["test_case_version_ids"]
    assert isinstance(ids, list)
    version = session.get(models.TestCaseVersion, ids[0])
    assert version is not None
    return version


def _approve(session: Session, workflow: AITestingWorkflow, generated: dict[str, object]) -> models.TestCaseVersion:
    tracker = workflow.tracker
    assert isinstance(tracker, LocalIssueTracker)
    issue_key, review_id = generated["issue_key"], generated["review_id"]
    assert isinstance(issue_key, str) and isinstance(review_id, str)
    tracker.set_issue_status(issue_key, "Approved")
    workflow.sync_review(review_id)
    session.commit()
    return _version(session, generated)


def test_same_provider_id_for_two_requirements_has_independent_identity_and_provenance(
    identity_session: Session,
) -> None:
    workflow = _workflow(identity_session)
    first = workflow.generate_tests("REQV-A")
    second = workflow.generate_tests("REQV-B")
    first_version, second_version = _version(identity_session, first), _version(identity_session, second)

    assert first["test_case_ids"] != second["test_case_ids"]
    assert first_version.test_case_id != second_version.test_case_id
    assert first_version.requirement_version_id == "REQV-A"
    assert second_version.requirement_version_id == "REQV-B"
    assert first_version.source_ai_run_id == first["generation_run_id"]
    assert second_version.source_ai_run_id == second["generation_run_id"]
    assert first_version.source_ai_run_id != second_version.source_ai_run_id
    assert first_version.content["provider_test_id"] == second_version.content["provider_test_id"] == "AI-TC-001"
    assert first_version.version == second_version.version == 1


def test_repeated_generation_creates_independent_test_cases(identity_session: Session) -> None:
    workflow = _workflow(identity_session)
    first = workflow.generate_tests("REQV-A")
    second = workflow.generate_tests("REQV-A")

    assert first["test_case_ids"] != second["test_case_ids"]
    assert first["test_case_version_ids"] != second["test_case_version_ids"]
    assert _version(identity_session, first).version == _version(identity_session, second).version == 1


def test_duplicate_provider_ids_in_one_batch_are_not_deduplicated(identity_session: Session) -> None:
    workflow = _workflow(identity_session, suite=_suite(
        _case(title="First distinct scenario"), _case(title="Second distinct scenario"),
    ))
    generated = workflow.generate_tests("REQV-A")

    assert generated["accepted_for_review"] == 2
    assert generated["provider_test_ids"] == ["AI-TC-001", "AI-TC-001"]
    assert len(set(generated["test_case_ids"])) == 2
    assert len(set(generated["test_case_version_ids"])) == 2
    review = identity_session.get(models.ReviewRequest, generated["review_id"])
    assert review is not None and review.artifact_ids == generated["test_case_version_ids"]


def test_approval_is_isolated_between_requirements(identity_session: Session) -> None:
    workflow = _workflow(identity_session, LocalIssueTracker())
    approved_result = workflow.generate_tests("REQV-A")
    pending_result = workflow.generate_tests("REQV-B")
    approved = _approve(identity_session, workflow, approved_result)
    pending = _version(identity_session, pending_result)

    assert approved.status == "APPROVED"
    assert identity_session.get(models.TestCase, approved.test_case_id).review_status == "APPROVED"
    assert pending.status == "REVIEW_REQUIRED"
    assert identity_session.get(models.TestCase, pending.test_case_id).review_status == "REVIEW_REQUIRED"


@pytest.mark.parametrize("status", ["REVIEW_REQUIRED", "REJECTED"])
def test_pending_and_rejected_generated_versions_are_not_executable(identity_session: Session, status: str) -> None:
    workflow = _workflow(identity_session)
    generated = workflow.generate_tests("REQV-A")
    version = _version(identity_session, generated)
    version.status = status
    identity_session.commit()

    with pytest.raises(WorkflowConflict, match="Only APPROVED"):
        workflow.execute("REQV-A", [version.test_case_version_id], {
            version.test_case_version_id: version.content["expected_result"],
        }, "identity-v1")


def test_approved_execution_preserves_result_parent_version_and_evidence(identity_session: Session) -> None:
    workflow = _workflow(identity_session, LocalIssueTracker())
    generated = workflow.generate_tests("REQV-A")
    version = _approve(identity_session, workflow, generated)
    executed = workflow.execute("REQV-A", [version.test_case_version_id], {
        version.test_case_version_id: version.content["expected_result"],
    }, "identity-v1")
    result = identity_session.scalar(select(models.TestResult).where(
        models.TestResult.test_run_id == executed["test_run_id"],
    ))

    assert executed["status"] == "PASSED" and executed["automatically_executed"] is False
    assert result is not None
    assert result.test_case_id == version.test_case_id
    assert result.test_case_version_id == version.test_case_version_id
    assert result.evidence["dataset_version_id"] == "DSV-IDENTITY-V1"
    assert result.evidence["result_source"] == "CALLER_SUBMITTED"


def test_failed_execution_keeps_rca_and_defect_traceability(identity_session: Session) -> None:
    tracker = LocalIssueTracker()
    workflow = _workflow(identity_session, tracker)
    generated = workflow.generate_tests("REQV-A")
    version = _approve(identity_session, workflow, generated)
    executed = workflow.execute("REQV-A", [version.test_case_version_id], {
        version.test_case_version_id: "observed mismatch",
    }, "identity-v1")
    result = identity_session.scalar(select(models.TestResult).where(
        models.TestResult.test_run_id == executed["test_run_id"],
    ))
    trace = workflow.traceability("REQV-A")

    assert executed["status"] == "FAILED" and executed["external_sync"] == ["SUCCEEDED"]
    assert result is not None and result.rca_ai_run_id is not None
    assert result.test_case_id == version.test_case_id
    assert result.test_case_version_id == version.test_case_version_id
    assert trace["test_case_versions"][0]["provider_test_id"] == "AI-TC-001"
    assert trace["test_results"][0]["test_case_id"] == version.test_case_id
    assert trace["test_results"][0]["rca_ai_run_id"] == result.rca_ai_run_id
    assert trace["rca_ai_runs"][0]["id"] == result.rca_ai_run_id
    defect = identity_session.get(models.ExternalIssueLink, result.external_issue_link_id)
    assert defect is not None and defect.artifact_id == str(result.result_id)
    assert defect.issue_key in tracker.issues


def test_generation_failure_rolls_back_all_prepared_records(identity_session: Session, monkeypatch) -> None:
    workflow = _workflow(identity_session)
    original_flush = identity_session.flush

    def fail_after_version_prepared(*args, **kwargs) -> None:
        if any(isinstance(item, models.TestCaseVersion) for item in identity_session.new):
            raise SQLAlchemyError("simulated generation persistence failure")
        original_flush(*args, **kwargs)

    monkeypatch.setattr(identity_session, "flush", fail_after_version_prepared)
    with pytest.raises(SQLAlchemyError, match="simulated generation persistence failure"):
        workflow.generate_tests("REQV-A")

    for model in (models.TestCase, models.TestCaseVersion, models.ReviewRequest, models.ExternalIssueLink):
        assert identity_session.scalar(select(func.count()).select_from(model)) == 0
    ai_run = identity_session.scalar(select(models.AIRun))
    assert ai_run is not None
    assert ai_run.status == "FAILED"
    assert ai_run.failure_stage == "generated_test_persistence"
    assert ai_run.output == {}


def test_external_tracker_failure_preserves_drafts_and_retry_state(identity_session: Session) -> None:
    class FailingTracker(LocalIssueTracker):
        def create_review_issue(self, *, summary: str, description: str, external_id: str) -> str:
            del summary, description, external_id
            raise RuntimeError("synthetic tracker outage")

    workflow = _workflow(identity_session, FailingTracker())
    generated = workflow.generate_tests("REQV-A")
    version = _version(identity_session, generated)
    link = identity_session.scalar(select(models.ExternalIssueLink))

    assert generated["sync_status"] == "FAILED" and version.status == "REVIEW_REQUIRED"
    assert identity_session.get(models.TestCase, version.test_case_id) is not None
    assert identity_session.get(models.ReviewRequest, generated["review_id"]) is not None
    assert link is not None and link.retry_count == 1
    assert "synthetic tracker outage" in link.sync_error


def test_concurrent_generation_uses_unique_platform_identities(tmp_path: Path) -> None:
    engine = _engine(f"sqlite+pysqlite:///{tmp_path / 'identity-concurrency.db'}")
    barrier = Barrier(2)

    def generate() -> tuple[str, str]:
        with Session(engine) as session:
            workflow = _workflow(session)
            barrier.wait(timeout=5)
            result = workflow.generate_tests("REQV-A")
            return result["test_case_ids"][0], result["test_case_version_ids"][0]

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            identities = list(executor.map(lambda _: generate(), range(2)))
        with Session(engine) as session:
            parents = session.scalars(select(models.TestCase)).all()
            versions = session.scalars(select(models.TestCaseVersion)).all()
            assert len(parents) == len(versions) == 2
            assert len({item[0] for item in identities}) == len({item[1] for item in identities}) == 2
            assert all(item.requirement_version_id == "REQV-A" for item in versions)
            assert all(item.content["provider_test_id"] == "AI-TC-001" for item in versions)
    finally:
        engine.dispose()
