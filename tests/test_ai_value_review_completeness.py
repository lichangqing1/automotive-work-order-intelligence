from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from automotive_quality.domains.ai.schemas import GeneratedTestCase, GeneratedTestSuite
from automotive_quality.domains.evaluation import ai_value
from automotive_quality.domains.evaluation.ai_value import TestReview as ReviewAssessment


@pytest.fixture(scope="module")
def experiment_module():
    script = Path(__file__).resolve().parents[1] / "scripts/run_ai_value_experiment.py"
    spec = importlib.util.spec_from_file_location("run_ai_value_experiment_completeness", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _queue(
    *,
    variant: str = "ai_assisted",
    case_id: str = "REQ-1",
    run_number: int = 1,
    test_id: str = "DISPLAY-1",
) -> dict:
    return {
        "variant": variant,
        "case_id": case_id,
        "run_number": run_number,
        "test_id": test_id,
    }


def _review(
    *,
    variant: str = "ai_assisted",
    case_id: str = "REQ-1",
    run_number: int = 1,
    test_id: str = "DISPLAY-1",
) -> ReviewAssessment:
    return ReviewAssessment(
        variant=variant,
        case_id=case_id,
        run_number=run_number,
        test_id=test_id,
        decision="APPROVED",
        validated_coverage=[],
        active_review_seconds=1,
    )


def _generated_case(test_id: str, title: str) -> GeneratedTestCase:
    return GeneratedTestCase(
        test_id=test_id,
        title=title,
        objective="Validate review identity",
        preconditions=[],
        test_data=[],
        steps=["Submit deterministic fixture"],
        expected_result="Fixture is accepted",
        category="positive",
        priority="P1",
    )


def test_unique_generated_identities_with_complete_reviews_are_complete(experiment_module) -> None:
    queue = [_queue(test_id="DISPLAY-1"), _queue(test_id="DISPLAY-2")]
    reviews = [_review(test_id="DISPLAY-1"), _review(test_id="DISPLAY-2")]

    summary = experiment_module.test_review_completeness(queue, reviews)

    assert summary["complete"] is True
    assert summary["expected_count"] == summary["actual_count"] == 2
    assert summary["duplicate_count"] == summary["expected_duplicate_count"] == 0
    assert summary["validation_errors"] == []


def test_duplicate_ids_within_generated_suite_are_rejected_before_queue_deduplication(
    experiment_module,
) -> None:
    suite = GeneratedTestSuite(
        requirement="Duplicate identity fixture",
        cases=[_generated_case("DUP-1", "First"), _generated_case("DUP-1", "Second")],
    )
    validator = getattr(ai_value, "validate_generated_test_identities", None)
    assert validator is not None

    with pytest.raises(
        ValueError,
        match=r"variant=ai_assisted.*case_id=REQ-1.*run_number=1.*test_id=DUP-1",
    ):
        validator(suite, variant="ai_assisted", case_id="REQ-1", run_number=1)

    summary = experiment_module.test_review_completeness(
        [_queue(test_id="DUP-1"), _queue(test_id="DUP-1")],
        [_review(test_id="DUP-1")],
    )
    assert summary["complete"] is False
    assert summary["expected_count"] == 2
    assert summary["expected_duplicate_count"] == 1


def test_duplicate_review_composite_identities_are_rejected(experiment_module) -> None:
    reviews = [_review(), _review()]
    validator = getattr(experiment_module, "validate_unique_test_reviews", None)
    assert validator is not None

    with pytest.raises(
        ValueError,
        match=r"variant=ai_assisted.*case_id=REQ-1.*run_number=1.*test_id=DISPLAY-1",
    ):
        validator(reviews)

    summary = experiment_module.test_review_completeness([_queue()], reviews)
    assert summary["complete"] is False
    assert summary["actual_count"] == 2
    assert summary["duplicate_count"] == 1
    assert "duplicate submitted review identity" in summary["validation_errors"][0]


def test_reused_display_ids_across_requirements_are_distinct(experiment_module) -> None:
    queue = [_queue(case_id="REQ-1"), _queue(case_id="REQ-2")]
    reviews = [_review(case_id="REQ-1"), _review(case_id="REQ-2")]

    summary = experiment_module.test_review_completeness(queue, reviews)

    assert summary["complete"] is True
    assert summary["expected_count"] == 2


def test_duplicate_baseline_identities_are_not_collapsed(experiment_module) -> None:
    queue = [
        _queue(variant="deterministic_baseline", test_id="BASE-1"),
        _queue(variant="deterministic_baseline", test_id="BASE-1"),
    ]
    reviews = [_review(variant="deterministic_baseline", test_id="BASE-1")]

    summary = experiment_module.test_review_completeness(queue, reviews)

    assert summary["complete"] is False
    assert summary["expected_count"] == 2
    assert summary["expected_duplicate_count"] == 1
    assert "variant=deterministic_baseline" in " ".join(summary["validation_errors"])


def test_missing_review_reports_its_non_sensitive_composite_identity(experiment_module) -> None:
    summary = experiment_module.test_review_completeness(
        [_queue(test_id="DISPLAY-1"), _queue(test_id="DISPLAY-2")],
        [_review(test_id="DISPLAY-1")],
    )

    assert summary["complete"] is False
    assert summary["missing_count"] == 1
    assert "test_id=DISPLAY-2" in " ".join(summary["validation_errors"])


def test_unexpected_review_reports_its_non_sensitive_composite_identity(experiment_module) -> None:
    summary = experiment_module.test_review_completeness(
        [_queue(test_id="DISPLAY-1")],
        [_review(test_id="DISPLAY-1"), _review(test_id="UNEXPECTED")],
    )

    assert summary["complete"] is False
    assert summary["unexpected_count"] == 1
    assert "test_id=UNEXPECTED" in " ".join(summary["validation_errors"])


def test_same_generated_display_id_in_multiple_runs_is_distinct(experiment_module) -> None:
    queue = [_queue(run_number=1), _queue(run_number=2)]
    reviews = [_review(run_number=1), _review(run_number=2)]

    summary = experiment_module.test_review_completeness(queue, reviews)

    assert summary["complete"] is True
    assert summary["expected_count"] == 2


def test_incomplete_review_cannot_be_marked_publishable(experiment_module) -> None:
    eligibility = getattr(experiment_module, "publication_eligible", None)
    assert eligibility is not None
    report = {
        "review_completeness": {"complete": False},
        "human_baseline_completeness": {"complete": True},
    }

    assert eligibility("openai", True, "test-generation", report) is False


@pytest.mark.parametrize(
    ("artifact_name", "experiment"),
    [("test_generation_report.json", "test-generation"), ("rca_report.json", "rca")],
)
def test_valid_existing_published_reports_remain_eligible(
    experiment_module,
    artifact_name: str,
    experiment: str,
) -> None:
    eligibility = getattr(experiment_module, "publication_eligible", None)
    assert eligibility is not None
    path = Path("artifacts/ai_value") / artifact_name
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["experiment"]["publishable"] is True
    assert eligibility("openai", True, experiment, report) is True
