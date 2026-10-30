from __future__ import annotations

from automotive_quality.baselines.evidence_rca import analyze_evidence
from automotive_quality.baselines.template_test_generator import generate_template_tests
from automotive_quality.domains.ai.schemas import AIRootCauseAnalysis, GeneratedTestCase, GeneratedTestSuite, RCAClaim
from automotive_quality.domains.evaluation.ai_value import (
    RCACase,
    RequirementCase,
    aggregate,
    load_jsonl,
    rca_metrics,
)
from automotive_quality.domains.evaluation.ai_value import (
    TestReview as ReviewAssessment,
)
from automotive_quality.domains.evaluation.ai_value import (
    test_generation_metrics as calculate_test_generation_metrics,
)


def test_curated_ai_value_datasets_have_variety_and_insufficient_evidence() -> None:
    requirements = load_jsonl("evaluation/ai_value/requirements.jsonl", RequirementCase)
    rca_cases = load_jsonl("evaluation/ai_value/rca_cases.jsonl", RCACase)

    assert len(requirements) >= 30
    assert {item.difficulty for item in requirements} == {"simple", "medium", "hard"}
    assert all(item.gold.risks and item.gold.scenarios for item in requirements)
    assert len(rca_cases) >= 30
    assert sum(not item.evidence_sufficient for item in rca_cases) >= 5


def test_deterministic_template_is_a_fair_multi_category_baseline() -> None:
    suite = generate_template_tests("The API and database must store a required timestamp consistently")

    assert {case.category for case in suite.cases} >= {"positive", "negative", "boundary", "integration", "data_quality"}
    assert all(case.steps and case.expected_result for case in suite.cases)


def test_generation_metrics_use_human_validated_coverage_and_review_effort() -> None:
    benchmark = load_jsonl("evaluation/ai_value/requirements.jsonl", RequirementCase)[0]
    suite = GeneratedTestSuite(requirement=benchmark.requirement, cases=[GeneratedTestCase(
        test_id="AI-1", title="Reject missing resolved_at", objective="Missing timestamp",
        preconditions=["Resolved order"], test_data=[], steps=["Submit"], expected_result="Rejected",
        category="negative", priority="P1", covers=["untrusted-model-claim"],
    )])
    reviews = [ReviewAssessment(
        case_id=benchmark.requirement_id, run_number=1, test_id="AI-1", decision="APPROVED_WITH_EDITS",
        validated_coverage=["missing_resolved_at"], active_review_seconds=25,
    )]

    metrics = calculate_test_generation_metrics(benchmark, suite, {"AI-1": reviews[0].validated_coverage}, reviews)

    assert metrics["requirement_coverage"] == 0.2
    assert metrics["negative_coverage"] == 0.5
    assert metrics["approval_rate"] == 1.0
    assert metrics["edit_rate"] == 1.0
    assert metrics["active_review_seconds"] == 25


def test_rca_baseline_is_evidence_grounded_and_abstains() -> None:
    cases = load_jsonl("evaluation/ai_value/rca_cases.jsonl", RCACase)
    supported = cases[0]
    insufficient = next(item for item in cases if not item.evidence_sufficient)

    supported_result = analyze_evidence(supported.evidence)
    abstention = analyze_evidence(insufficient.evidence)

    assert rca_metrics(supported, supported_result)["root_cause_accuracy"] == 1.0
    assert rca_metrics(supported, supported_result)["evidence_support_rate"] == 1.0
    assert abstention.insufficient_evidence
    assert rca_metrics(insufficient, abstention)["correct_abstention"] == 1.0


def test_rca_distinguishes_valid_citations_from_correct_support() -> None:
    benchmark = RCACase(
        case_id="RCA-X", failure_class="OTA_COMPATIBILITY",
        ground_truth_root_cause="unsupported_software_version", evidence_sufficient=True,
        evidence=[{"id": "EV-1", "fact": "Version is unsupported."}, {"id": "EV-2", "fact": "Battery is charged."}],
        supporting_evidence_ids=["EV-1"],
    )
    result = AIRootCauseAnalysis(
        failure_class="OTA_COMPATIBILITY", probable_root_causes=["unsupported_software_version"],
        supporting_evidence=["EV-2"], recommended_checks=[], confidence=0.8,
        insufficient_evidence=False, claims=[RCAClaim(claim="unsupported_software_version", evidence_ids=["EV-2"])],
    )

    metrics = rca_metrics(benchmark, result)

    assert metrics["citation_validity_rate"] == 1.0
    assert metrics["evidence_correctness_rate"] == 0.0
    assert metrics["evidence_support_rate"] == 0.0
    assert metrics["unsupported_claim_rate"] == 1.0


def test_aggregate_reports_required_statistical_context() -> None:
    summary = aggregate([{"coverage": 0.5}, {"coverage": 1.0}, {"coverage": 0.75}])["coverage"]

    assert summary["n"] == 3
    assert summary["mean"] == 0.75
    assert summary["median"] == 0.75
    assert summary["min"] == 0.5
    assert summary["max"] == 1.0
    assert summary["stddev"] > 0
