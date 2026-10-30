from automotive_quality.domains.testing.models import TestCase as CaseSpec
from automotive_quality.domains.testing.models import TestResult as ExecutionResult
from automotive_quality.domains.testing.models import TestRunStatus as RunStatus
from automotive_quality.domains.testing.service import InMemoryTestRunRepository
from automotive_quality.domains.testing.service import TestExecutionService as ExecutionService


def _case(case_id: str) -> CaseSpec:
    return CaseSpec(test_case_id=case_id, title="Validate order", suite="OTA_REGRESSION", expected="valid")


def test_execution_persists_passed_run() -> None:
    repository = InMemoryTestRunRepository()
    service = ExecutionService(repository)
    run = service.execute("OTA_REGRESSION", [_case("TC-1")], lambda case: ExecutionResult(test_case_id=case.test_case_id, status=RunStatus.PASSED, expected="valid", actual="valid"))
    assert run.status == RunStatus.PASSED
    assert run.summary["passed"] == 1
    assert repository.get(run.test_run_id) == run


def test_any_failure_fails_run_with_evidence() -> None:
    repository = InMemoryTestRunRepository()
    service = ExecutionService(repository)
    cases = [_case("TC-1"), _case("TC-2")]
    def execute(case: CaseSpec) -> ExecutionResult:
        status = RunStatus.FAILED if case.test_case_id == "TC-2" else RunStatus.PASSED
        return ExecutionResult(test_case_id=case.test_case_id, status=status, expected="valid", actual="invalid" if status == RunStatus.FAILED else "valid", affected_rows=3 if status == RunStatus.FAILED else 0)
    run = service.execute("OTA_REGRESSION", cases, execute)
    assert run.status == RunStatus.FAILED
    assert run.summary == {"test_run_id": run.test_run_id, "status": RunStatus.FAILED, "total": 2, "passed": 1, "failed": 1}


def test_executor_exception_becomes_durable_error_result() -> None:
    repository = InMemoryTestRunRepository()
    service = ExecutionService(repository)

    def explode(case: CaseSpec) -> ExecutionResult:
        raise RuntimeError(f"cannot execute {case.test_case_id}")

    run = service.execute("OTA_REGRESSION", [_case("TC-ERR")], explode)
    assert run.status == RunStatus.ERROR
    assert run.results[0].status == "ERROR"
    assert repository.get(run.test_run_id) == run
