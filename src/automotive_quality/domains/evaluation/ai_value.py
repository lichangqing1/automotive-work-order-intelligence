from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from automotive_quality.domains.ai.schemas import AIRootCauseAnalysis, GeneratedTestSuite


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
    known_evidence = {item.id for item in case.evidence}
    correct_evidence = set(case.supporting_evidence_ids)
    claims = result.claims
    cited = [evidence_id for claim in claims for evidence_id in claim.evidence_ids]
    valid = [evidence_id for evidence_id in cited if evidence_id in known_evidence]
    supported = [evidence_id for evidence_id in cited if evidence_id in correct_evidence]
    predicted_causes = {item.casefold() for item in result.probable_root_causes} | {item.claim.casefold() for item in claims}
    expected = case.ground_truth_root_cause.casefold() if case.ground_truth_root_cause else None
    correct_abstention = (not case.evidence_sufficient and result.insufficient_evidence)
    return {
        "failure_class_accuracy": float(result.failure_class.casefold() == case.failure_class.casefold()),
        "root_cause_accuracy": float(expected is not None and any(expected in cause or cause in expected for cause in predicted_causes)),
        "citation_validity_rate": _ratio(len(valid), len(cited)) if cited else float(not claims),
        "evidence_support_rate": _ratio(len(supported), len(cited)) if cited else float(not claims),
        "evidence_correctness_rate": _ratio(len(supported), len(cited)) if cited else float(not claims),
        "unsupported_claim_rate": _ratio(len(cited) - len(supported), len(cited)) if cited else 0.0,
        "correct_abstention": float(correct_abstention),
    }


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
