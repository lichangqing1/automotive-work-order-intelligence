from __future__ import annotations

import hashlib
import json
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from automotive_quality.domains.ai.schemas import AIRootCauseAnalysis, GeneratedTestSuite

RCA_METRIC_VERSION = "rca-metrics-v2"


class GoldScenario(BaseModel):
    id: str
    type: Literal["positive", "negative", "boundary", "integration", "data_quality", "exception"]
    match_terms: list[str] = Field(min_length=1)


class RequirementGold(BaseModel):
    risks: list[str]
    scenarios: list[GoldScenario]


class RequirementCase(BaseModel):
    requirement_id: str
    requirement: str
    difficulty: Literal["simple", "medium", "hard"]
    gold: RequirementGold


class EvidenceItem(BaseModel):
    id: str
    fact: str


class RCACase(BaseModel):
    case_id: str
    failure_class: str
    ground_truth_root_cause: str | None
    equivalent_root_causes: list[str] = Field(default_factory=list)
    evidence_sufficient: bool
    evidence: list[EvidenceItem]
    supporting_evidence_ids: list[str]


class TestReview(BaseModel):
    variant: Literal["deterministic_baseline", "ai_assisted"] = "ai_assisted"
    case_id: str
    run_number: int
    test_id: str
    decision: Literal["APPROVED", "APPROVED_WITH_EDITS", "REJECTED"]
    validated_coverage: list[str]
    rejection_reasons: list[Literal[
        "schema_invalid", "unsupported_assumption", "requirement_contradiction",
        "unexecutable_step", "missing_expected_result", "duplicate", "irrelevant_scenario",
    ]] = Field(default_factory=list)
    active_review_seconds: float = Field(ge=0)


class RCAReview(BaseModel):
    case_id: str
    run_number: int
    baseline_investigation_seconds: float = Field(ge=0)
    recommended_check_usefulness: float = Field(ge=0, le=1)
    active_investigation_seconds: float = Field(ge=0)


class HumanTestDesignMeasurement(BaseModel):
    case_id: str
    active_design_seconds: float = Field(gt=0)
    validated_coverage: list[str]


def validate_generated_test_identities(
    suite: GeneratedTestSuite,
    *,
    variant: str,
    case_id: str,
    run_number: int,
) -> None:
    counts = Counter(case.test_id for case in suite.cases)
    duplicates = sorted(test_id for test_id, count in counts.items() if count > 1)
    if duplicates:
        identities = "; ".join(
            f"variant={variant}, case_id={case_id}, run_number={run_number}, test_id={test_id}"
            for test_id in duplicates
        )
        raise ValueError(f"Duplicate generated review identity: {identities}")


def load_jsonl(path: str | Path, model: type[BaseModel]) -> list[Any]:
    rows = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                rows.append(model.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"Invalid benchmark row {path}:{line_number}: {exc}") from exc
    if not rows:
        raise ValueError(f"Benchmark dataset is empty: {path}")
    return rows


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def suggested_coverage(suite: GeneratedTestSuite, gold: RequirementGold) -> dict[str, list[str]]:
    """Suggest mappings for review; these labels are never treated as human validated."""
    mapping: dict[str, list[str]] = {}
    for case in suite.cases:
        text = " ".join((case.title, case.objective, case.expected_result, *case.steps)).casefold()
        mapping[case.test_id] = [scenario.id for scenario in gold.scenarios if all(term.casefold() in text for term in scenario.match_terms)]
    return mapping


def test_generation_metrics(
    benchmark: RequirementCase,
    suite: GeneratedTestSuite,
    validated_coverage: dict[str, list[str]],
    reviews: list[TestReview] | None = None,
) -> dict[str, float]:
    scenario_by_id = {scenario.id: scenario for scenario in benchmark.gold.scenarios}
    covered = {scenario_id for values in validated_coverage.values() for scenario_id in values if scenario_id in scenario_by_id}
    metrics = {
        "requirement_coverage": _ratio(len(covered), len(scenario_by_id)),
        "boundary_coverage": _typed_coverage("boundary", covered, scenario_by_id),
        "negative_coverage": _typed_coverage("negative", covered, scenario_by_id),
        "integration_coverage": _typed_coverage("integration", covered, scenario_by_id),
        "data_quality_coverage": _typed_coverage("data_quality", covered, scenario_by_id),
        "schema_validity": 1.0,
        "duplicate_rate": _duplicate_rate(suite),
        "unsupported_assumption_rate": _ratio(sum(bool(case.unsupported_assumptions) for case in suite.cases), len(suite.cases)),
        "executable_rate": _ratio(sum(bool(case.steps and case.expected_result.strip()) for case in suite.cases), len(suite.cases)),
    }
    if reviews is not None:
        approved = [item for item in reviews if item.decision != "REJECTED"]
        metrics.update({
            "approval_rate": _ratio(len(approved), len(reviews)),
            "edit_rate": _ratio(sum(item.decision == "APPROVED_WITH_EDITS" for item in reviews), len(reviews)),
            "rejection_rate": _ratio(sum(item.decision == "REJECTED" for item in reviews), len(reviews)),
            "active_review_seconds": sum(item.active_review_seconds for item in reviews),
        })
    return metrics


def rca_metrics(case: RCACase, result: AIRootCauseAnalysis) -> dict[str, float]:
    """Score deterministic identity and claim-level evidence properties.

    Root-cause identity accepts only normalized exact labels declared by the
    benchmark. Evidence support is structural: a claim is supported when it
    cites a benchmark-designated supporting evidence ID. It does not assert
    semantic entailment beyond that curated mapping.
    """
    known_evidence = {item.id for item in case.evidence}
    correct_evidence = set(case.supporting_evidence_ids) & known_evidence
    claims = result.claims
    cited = [
        (claim_number, evidence_id)
        for claim_number, claim in enumerate(claims)
        for evidence_id in set(claim.evidence_ids)
    ]
    valid = [pair for pair in cited if pair[1] in known_evidence]
    correct = [pair for pair in cited if pair[1] in correct_evidence]

    accepted_causes = set()
    if case.ground_truth_root_cause is not None:
        accepted_causes = {
            _normalize_rca_label(item)
            for item in (case.ground_truth_root_cause, *case.equivalent_root_causes)
        }
    predicted_causes = {_normalize_rca_label(item) for item in result.probable_root_causes}
    root_cause_correct = bool(predicted_causes) and predicted_causes <= accepted_causes

    assertion_count = max(len(claims), len(result.probable_root_causes))
    evidence_grounding_allowed = not result.probable_root_causes or root_cause_correct
    supported_claims = sum(
        evidence_grounding_allowed
        and bool(set(claim.evidence_ids) & correct_evidence)
        for claim in claims
    )
    correct_abstention = (
        not case.evidence_sufficient
        and result.insufficient_evidence
        and assertion_count == 0
    )
    no_assertion_score = float(correct_abstention)
    return {
        "failure_class_accuracy": float(
            _normalize_rca_label(result.failure_class) == _normalize_rca_label(case.failure_class)
        ),
        "root_cause_accuracy": float(root_cause_correct),
        "citation_validity_rate": _ratio(len(valid), len(cited)) if cited else no_assertion_score,
        "evidence_support_rate": (
            _ratio(supported_claims, assertion_count) if assertion_count else no_assertion_score
        ),
        "evidence_correctness_rate": (
            _ratio(len(correct), len(cited)) if cited else no_assertion_score
        ),
        "unsupported_claim_rate": (
            _ratio(assertion_count - supported_claims, assertion_count) if assertion_count else 0.0
        ),
        "correct_abstention": float(correct_abstention),
    }


def _normalize_rca_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "_", normalized).strip("_")


def aggregate(per_case: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    names = sorted({name for row in per_case for name in row})
    result: dict[str, dict[str, float]] = {}
    for name in names:
        values = [row[name] for row in per_case if name in row]
        result[name] = {
            "n": float(len(values)), "mean": statistics.fmean(values), "median": statistics.median(values),
            "stddev": statistics.pstdev(values), "min": min(values), "max": max(values),
        }
    return result


def _typed_coverage(kind: str, covered: set[str], scenario_by_id: dict[str, GoldScenario]) -> float:
    expected = {scenario_id for scenario_id, scenario in scenario_by_id.items() if scenario.type == kind}
    return _ratio(len(expected & covered), len(expected)) if expected else 1.0


def _duplicate_rate(suite: GeneratedTestSuite) -> float:
    signatures = [" ".join(case.title.casefold().split()) for case in suite.cases]
    return _ratio(len(signatures) - len(set(signatures)), len(signatures))


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def write_json(path: str | Path, value: Any) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: str | Path, values: list[dict[str, Any]]) -> None:
    Path(path).write_text("".join(json.dumps(value, sort_keys=True) + "\n" for value in values), encoding="utf-8")
