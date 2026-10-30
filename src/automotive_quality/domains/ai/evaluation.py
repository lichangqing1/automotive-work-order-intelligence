from __future__ import annotations

import json
from pathlib import Path

from automotive_quality.domains.evaluation.policy import Policy, evaluate_policies

from .providers.mock import MockProvider
from .schemas import AIRootCauseAnalysis, RequirementAnalysis
from .workflows import AIWorkflowService


def evaluate_mock_baseline(dataset_path: str | Path) -> dict[str, dict[str, float]]:
    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    requirement_case = dataset["requirements"][0]
    provider = MockProvider({
        RequirementAnalysis: {
            "business_rules": ["Resolved OTA work orders require supported versions and timestamps"],
            "risks": requirement_case["expected_risks"], "boundary_conditions": ["First supported version"],
            "missing_information": [], "recommended_test_scenarios": ["Reject unsupported version", "Reject missing timestamp"],
        },
        AIRootCauseAnalysis: {
            "failure_class": "UNKNOWN", "probable_root_causes": [], "supporting_evidence": [],
            "recommended_checks": ["Collect evidence"], "confidence": 0.0, "insufficient_evidence": True,
        },
    })
    service = AIWorkflowService(provider)
    analysis = service.analyze_requirement(requirement_case["text"])
    expected = {item.casefold() for item in requirement_case["expected_risks"]}
    actual = {item.casefold() for item in analysis.risks}
    refusal = service.analyze_rca(dataset["rca"][0]["evidence"])
    return {
        "requirement": {"schema_validity": 1.0, "risk_coverage": len(expected & actual) / len(expected)},
        "rca": {"refusal_correctness": float(refusal.insufficient_evidence)},
    }


def evaluate_ai_policies(metrics: dict, policy_path: str | Path) -> dict:
    import yaml

    config = yaml.safe_load(Path(policy_path).read_text(encoding="utf-8"))
    evaluations = evaluate_policies(metrics, [Policy.model_validate(item) for item in config["policies"]])
    return {"passed": all(item.passed for item in evaluations), "evaluations": [item.model_dump() for item in evaluations]}

