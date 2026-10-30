from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from automotive_quality.domains.testing.models import TestResult as DomainTestResult
from automotive_quality.domains.testing.models import TestRun as DomainTestRun

from . import models


class PostgresTestRunRepository:
    """SQLAlchemy repository; production URLs use PostgreSQL, tests may use SQLite."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, run: DomainTestRun) -> None:
        record = self.session.get(models.TestRun, run.test_run_id)
        if record is None:
            record = models.TestRun(test_run_id=run.test_run_id, suite=run.suite, environment=run.environment, status=run.status)
            self.session.add(record)
        record.status = run.status
        record.started_at = run.started_at
        record.completed_at = run.completed_at
        existing = {item.test_case_id: item for item in self.session.scalars(select(models.TestResult).where(models.TestResult.test_run_id == run.test_run_id))}
        for result in run.results:
            if result.test_case_id not in existing:
                self.session.add(models.TestResult(
                    test_run_id=run.test_run_id, test_case_id=result.test_case_id, status=result.status,
                    expected=result.expected, actual=result.actual, affected_rows=result.affected_rows,
                    execution_ms=result.execution_ms, evidence=result.evidence,
                ))
            else:
                record_result = existing[result.test_case_id]
                record_result.status = result.status
                record_result.expected = result.expected
                record_result.actual = result.actual
                record_result.affected_rows = result.affected_rows
                record_result.execution_ms = result.execution_ms
                record_result.evidence = result.evidence
        self.session.flush()

    def get(self, run_id: str) -> DomainTestRun | None:
        record = self.session.get(models.TestRun, run_id)
        if record is None:
            return None
        results = self.session.scalars(select(models.TestResult).where(models.TestResult.test_run_id == run_id)).all()
        return DomainTestRun(
            test_run_id=record.test_run_id, suite=record.suite, status=record.status,
            environment=record.environment, created_at=record.created_at,
            started_at=record.started_at, completed_at=record.completed_at,
            results=[DomainTestResult(
                test_case_id=item.test_case_id, status=item.status, expected=item.expected,
                actual=item.actual, affected_rows=item.affected_rows, evidence=item.evidence or {},
                execution_ms=item.execution_ms,
            ) for item in results],
        )

    def list(self) -> list[DomainTestRun]:
        ids = self.session.scalars(select(models.TestRun.test_run_id).order_by(models.TestRun.created_at.desc())).all()
        return [run for run_id in ids if (run := self.get(run_id)) is not None]


class DQRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, run_id: str, dataset_version: str) -> models.DQRun:
        run = models.DQRun(run_id=run_id, dataset_version=dataset_version, status="RUNNING", started_at=datetime.now(timezone.utc))
        self.session.add(run)
        self.session.flush()
        return run

    def add_result(self, run_id: str, rule_id: str, rule_version_id: int, status: str, failed_count: int, evidence: dict[str, Any]) -> None:
        self.session.add(models.DQResult(run_id=run_id, rule_id=rule_id, rule_version_id=rule_version_id, status=status, failed_count=failed_count, evidence=evidence))

    def complete(self, run_id: str, passed: bool) -> None:
        run = self.session.get(models.DQRun, run_id)
        if run is None:
            raise KeyError(run_id)
        run.status = "PASSED" if passed else "FAILED"
        run.completed_at = datetime.now(timezone.utc)
        self.session.flush()


class EvaluationRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, run_id: str, dataset_name: str, dataset_version: str, metrics: dict[str, float], **metadata: Any) -> None:
        run = models.EvaluationRun(
            evaluation_run_id=run_id, dataset_name=dataset_name, dataset_version=dataset_version,
            status="SUCCEEDED", started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
            **metadata,
        )
        self.session.add(run)
        self.session.flush()
        self.session.add_all([models.EvaluationMetric(evaluation_run_id=run_id, metric_name=name, metric_value=value) for name, value in metrics.items()])


class AIRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, **values: Any) -> str:
        record = models.AIRun(**values)
        self.session.add(record)
        self.session.flush()
        return record.run_id
