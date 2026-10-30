from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from automotive_quality.domains.testing.models import TestResult as ExecutionResult
from automotive_quality.domains.testing.models import TestRun as ExecutionRun
from automotive_quality.domains.testing.models import TestRunStatus as RunStatus
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.database.repositories import PostgresTestRunRepository


def test_test_run_survives_new_repository_instance() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(models.TestCase(test_case_id="TC-1", suite="OTA", title="Check", severity="P1", specification={}, review_status="APPROVED"))
        run = ExecutionRun(test_run_id="TR-1", suite="OTA", status=RunStatus.FAILED, results=[ExecutionResult(test_case_id="TC-1", status=RunStatus.FAILED, expected="10", actual="7", affected_rows=3)])
        PostgresTestRunRepository(session).save(run)
        session.commit()
    with Session(engine) as restarted_session:
        restored = PostgresTestRunRepository(restarted_session).get("TR-1")
        assert restored is not None
        assert restored.summary["failed"] == 1
        assert restored.results[0].affected_rows == 3
