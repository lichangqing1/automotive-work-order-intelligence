from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from automotive_quality.application.ai_testing_workflow import AITestingWorkflow
from automotive_quality.domains.ai.workflows import AIWorkflowService
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.repositories import AIRunRepository
from automotive_quality.integrations.issue_tracker import LocalIssueTracker


def _engine():
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL integration database is not configured")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        if connection.exec_driver_sql("select current_database()").scalar_one() != "automotive_verify":
            pytest.fail("B3 integration tests require the isolated automotive_verify database")
    return engine


class FailingProvider:
    name = "postgres-fixture"
    model = "postgres-fixture"

    def generate_structured(self, *, prompt, response_model):
        del prompt, response_model
        raise TimeoutError("token=must-not-persist")


@pytest.mark.postgres
def test_postgres_provider_failure_audit_survives_caller_rollback() -> None:
    engine = _engine()
    with Session(engine) as session:
        service = AIWorkflowService(FailingProvider(), AIRunRepository(session))
        with pytest.raises(TimeoutError):
            service.analyze_requirement("postgres audit durability")
        run_id = service.last_run_id
        session.rollback()
    with Session(engine) as verify:
        record = verify.get(models.AIRun, run_id)
        assert record is not None and record.status == "FAILED"
        assert record.failure_stage == "provider_invocation"
        assert record.error_category == "PROVIDER_TIMEOUT"
        assert record.output == {}
        assert "must-not-persist" not in (record.error_message or "")
    engine.dispose()


@pytest.mark.postgres
def test_postgres_business_rollback_preserves_failed_ai_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _engine()
    suffix = uuid4().hex[:12]
    requirement_id = f"REQV-B3-{suffix}"
    with Session(engine) as setup:
        setup.add(models.RequirementVersion(
            requirement_version_id=requirement_id, requirement_id=f"REQ-B3-{suffix}", version=1,
            external_system="LOCAL", external_reference=f"B3-{suffix}", summary="B3 requirement",
            description="B3 description", acceptance_criteria="B3", content_hash="b" * 64,
        ))
        setup.commit()

    fail_business_flush = False

    class SignalingProvider:
        name = "postgres-fixture"
        model = "postgres-fixture"

        def generate_structured(self, *, prompt, response_model):
            nonlocal fail_business_flush
            del prompt
            fail_business_flush = True
            return response_model.model_validate({
                "business_rules": ["Rule"], "risks": ["Risk"],
                "boundary_conditions": ["Boundary"], "missing_information": [],
                "recommended_test_scenarios": ["Scenario"],
            })

    with Session(engine) as session:
        service = AIWorkflowService(SignalingProvider(), AIRunRepository(session))
        workflow = AITestingWorkflow(session, service, LocalIssueTracker(), {"Approved"}, {"Rejected"})
        original_flush = session.flush

        def controlled_flush(*args, **kwargs):
            if fail_business_flush:
                raise SQLAlchemyError("password=must-not-persist")
            return original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", controlled_flush)
        with pytest.raises(SQLAlchemyError):
            workflow.analyze(requirement_id)
        run_id = service.last_run_id

    with Session(engine) as verify:
        requirement = verify.get(models.RequirementVersion, requirement_id)
        record = verify.get(models.AIRun, run_id)
        assert requirement is not None and requirement.analysis is None
        assert record is not None and record.status == "FAILED" and record.output == {}
        assert record.failure_stage == "requirement_analysis_persistence"
        assert record.error_category == "DATABASE_ERROR"
        assert "must-not-persist" not in (record.error_message or "")
        assert verify.scalar(select(models.AIRun.run_id).where(models.AIRun.run_id == run_id)) == run_id
    engine.dispose()
