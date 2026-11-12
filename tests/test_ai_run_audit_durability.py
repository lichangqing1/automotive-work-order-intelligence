from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from automotive_quality.application.ai_testing_workflow import AITestingWorkflow
from automotive_quality.domains.ai.providers.mock import MockProvider
from automotive_quality.domains.ai.schemas import RequirementAnalysis
from automotive_quality.domains.ai.workflows import AIWorkflowService
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.database.repositories import (
    AIRunAuditPersistenceError,
    AIRunRepository,
)
from automotive_quality.integrations.issue_tracker import LocalIssueTracker


def _engine(tmp_path: Path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'ai-audit.db'}", poolclass=NullPool)
    Base.metadata.create_all(engine)
    return engine


def _analysis() -> dict[str, list[str]]:
    return {
        "business_rules": ["Resolved orders require evidence"],
        "risks": ["Missing evidence"],
        "boundary_conditions": ["First supported version"],
        "missing_information": [],
        "recommended_test_scenarios": ["Reject missing evidence"],
    }


class FailingProvider:
    name = "fixture"
    model = "fixture"

    def generate_structured(self, *, prompt, response_model):
        del prompt, response_model
        raise TimeoutError("api_key=secret-value token=private-value")


def test_provider_failure_audit_survives_business_rollback(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        service = AIWorkflowService(FailingProvider(), AIRunRepository(session))
        with pytest.raises(TimeoutError):
            service.analyze_requirement("synthetic requirement")
        session.rollback()
    with Session(engine) as verify:
        record = verify.scalar(select(models.AIRun))
        assert record is not None and record.status == "FAILED"
        assert record.failure_stage == "provider_invocation"
        assert record.error_category == "PROVIDER_TIMEOUT"
        assert record.output == {} and record.schema_valid is False
        assert "secret-value" not in (record.error_message or "")
        assert "private-value" not in (record.error_message or "")


def test_invalid_provider_response_is_durable_and_not_successful(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        service = AIWorkflowService(
            MockProvider({RequirementAnalysis: {"business_rules": "invalid"}}),
            AIRunRepository(session),
        )
        with pytest.raises(ValidationError):
            service.analyze_requirement("synthetic requirement")
        session.rollback()
    with Session(engine) as verify:
        record = verify.scalar(select(models.AIRun))
        assert record is not None and record.status == "FAILED"
        assert record.failure_stage == "provider_response_validation"
        assert record.error_category == "INVALID_PROVIDER_RESPONSE"
        assert record.output == {} and record.schema_valid is False


def test_business_failure_rolls_back_output_but_marks_ai_audit_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as setup:
        setup.add(models.RequirementVersion(
            requirement_version_id="REQV-B3", requirement_id="REQ-B3", version=1,
            external_system="LOCAL", external_reference="B3", summary="B3 requirement",
            description="B3 description", acceptance_criteria="B3", content_hash="a" * 64,
        ))
        setup.commit()
    with Session(engine) as session:
        fail_business_flush = False

        class SignalingProvider:
            name = "mock"
            model = "deterministic-fixture"

            def generate_structured(self, *, prompt, response_model):
                nonlocal fail_business_flush
                del prompt
                fail_business_flush = True
                return response_model.model_validate(_analysis())

        service = AIWorkflowService(
            SignalingProvider(),
            AIRunRepository(session),
        )
        workflow = AITestingWorkflow(session, service, LocalIssueTracker(), {"Approved"}, {"Rejected"})
        original_flush = session.flush

        def controlled_flush(*args, **kwargs):
            if fail_business_flush:
                raise SQLAlchemyError("password=secret-value")
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", controlled_flush)
        with pytest.raises(SQLAlchemyError):
            workflow.analyze("REQV-B3")
    with Session(engine) as verify:
        requirement = verify.get(models.RequirementVersion, "REQV-B3")
        record = verify.scalar(select(models.AIRun))
        assert requirement is not None and requirement.analysis is None
        assert record is not None and record.status == "FAILED" and record.output == {}
        assert record.failure_stage == "requirement_analysis_persistence"
        assert record.error_category == "DATABASE_ERROR"
        assert "secret-value" not in (record.error_message or "")


def test_audit_persistence_failure_never_reports_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        repository = AIRunRepository(session)
        service = AIWorkflowService(MockProvider({RequirementAnalysis: _analysis()}), repository)
        monkeypatch.setattr(repository, "save", lambda **values: (_ for _ in ()).throw(
            AIRunAuditPersistenceError("AI run audit persistence failed")
        ))
        with pytest.raises(AIRunAuditPersistenceError, match="AI run audit persistence failed"):
            service.analyze_requirement("synthetic requirement")
        assert session.scalar(select(func.count()).select_from(models.AIRun)) == 0


def test_retries_preserve_distinct_runs_with_stable_correlation(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    with Session(engine) as session:
        service = AIWorkflowService(FailingProvider(), AIRunRepository(session))
        for _ in range(2):
            with pytest.raises(TimeoutError):
                service.analyze_requirement("same synthetic requirement")
            session.rollback()
    with Session(engine) as verify:
        records = verify.scalars(select(models.AIRun).order_by(models.AIRun.created_at)).all()
        assert len(records) == 2
        assert len({record.run_id for record in records}) == 2
        assert len({record.correlation_id for record in records}) == 1
        assert all(record.status == "FAILED" for record in records)
