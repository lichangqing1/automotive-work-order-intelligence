from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from .models import TestCase, TestResult, TestResultStatus, TestRun, TestRunStatus


class InMemoryTestRunRepository:
    def __init__(self) -> None:
        self._runs: dict[str, TestRun] = {}

    def save(self, run: TestRun) -> None:
        self._runs[run.test_run_id] = run

    def get(self, run_id: str) -> TestRun | None:
        return self._runs.get(run_id)

    def list(self) -> list[TestRun]:
        return sorted(self._runs.values(), key=lambda run: run.created_at, reverse=True)


class TestExecutionService:
    def __init__(self, repository: InMemoryTestRunRepository) -> None:
        self.repository = repository

    def execute(self, suite: str, cases: list[TestCase], executor: Callable[[TestCase], TestResult]) -> TestRun:
        run = TestRun(test_run_id=f"TR-{uuid4().hex[:12].upper()}", suite=suite, status=TestRunStatus.RUNNING, started_at=datetime.now(timezone.utc))
        self.repository.save(run)
        results: list[TestResult] = []
        try:
            for case in cases:
                try:
                    results.append(executor(case))
                except Exception as exc:  # noqa: BLE001 - executor failures become durable ERROR results
                    results.append(TestResult(
                        test_case_id=case.test_case_id, status=TestResultStatus.ERROR,
                        expected=case.expected, actual=f"{type(exc).__name__}: {exc}",
                        evidence={"exception_type": type(exc).__name__},
                    ))
                run = run.model_copy(update={"results": results})
                self.repository.save(run)
            has_error = any(result.status == TestResultStatus.ERROR for result in results)
            has_failure = any(result.status in {TestResultStatus.FAILED, TestResultStatus.BLOCKED} for result in results)
            status = TestRunStatus.ERROR if has_error else TestRunStatus.FAILED if has_failure else TestRunStatus.PASSED
        finally:
            run = run.model_copy(update={"results": results, "status": locals().get("status", TestRunStatus.ERROR), "completed_at": datetime.now(timezone.utc)})
            self.repository.save(run)
        return run
