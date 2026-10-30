from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TestRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"


class TestResultStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    BLOCKED = "BLOCKED"


class TestCase(BaseModel):
    test_case_id: str
    title: str
    suite: str
    expected: str
    severity: str = "P2"
    version: int = 1


class TestResult(BaseModel):
    test_case_id: str
    status: TestResultStatus
    expected: str
    actual: str
    affected_rows: int = 0
    evidence: dict[str, Any] = Field(default_factory=dict)
    execution_ms: float = 0


class TestRun(BaseModel):
    test_run_id: str
    suite: str
    status: TestRunStatus = TestRunStatus.PENDING
    environment: str = "local"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    results: list[TestResult] = Field(default_factory=list)

    @property
    def summary(self) -> dict[str, int | str]:
        passed = sum(item.status == TestResultStatus.PASSED for item in self.results)
        failed = sum(item.status in {TestResultStatus.FAILED, TestResultStatus.ERROR} for item in self.results)
        return {"test_run_id": self.test_run_id, "status": self.status, "total": len(self.results), "passed": passed, "failed": failed}
