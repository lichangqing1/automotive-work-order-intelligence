import pytest
from pydantic import ValidationError

from automotive_quality.domains.ai.providers.mock import MockProvider
from automotive_quality.domains.ai.schemas import (
    AIRootCauseAnalysis,
    GeneratedTestSuite,
    RequirementAnalysis,
    RuleDraft,
)
from automotive_quality.domains.ai.workflows import AIWorkflowService


def _analysis() -> dict:
    return {"business_rules": ["Resolved OTA orders require a timestamp"], "risks": ["Missing evidence"], "boundary_conditions": ["First supported version"], "missing_information": [], "recommended_test_scenarios": ["Reject missing timestamp"]}


def test_requirement_analysis_is_schema_validated() -> None:
    result = AIWorkflowService(MockProvider({RequirementAnalysis: _analysis()})).analyze_requirement("Resolved OTA orders require timestamps")
    assert result.risks == ["Missing evidence"]


def test_generated_tests_remain_review_required() -> None:
    provider = MockProvider({GeneratedTestSuite: {"requirement": "OTA requirement", "cases": [{"test_id": "AI-TC-1", "title": "Missing timestamp", "objective": "Validate rejection", "preconditions": [], "test_data": [{"name": "resolved_at", "value": None}], "steps": ["Submit resolved order"], "expected_result": "Order fails deterministic DQ rule", "category": "negative", "priority": "P1"}]}})
    result = AIWorkflowService(provider).generate_tests("OTA requirement", RequirementAnalysis.model_validate(_analysis()))
    assert result.cases[0].review_status == "REVIEW_REQUIRED"


def test_generated_test_data_schema_uses_explicit_closed_entries() -> None:
    schema = GeneratedTestSuite.model_json_schema()
    test_data = schema["$defs"]["GeneratedTestCase"]["properties"]["test_data"]
    entry = schema["$defs"]["TestDataEntry"]

    assert test_data["type"] == "array"
    assert test_data["items"] == {"$ref": "#/$defs/TestDataEntry"}
    assert entry["additionalProperties"] is False
    assert set(entry["required"]) == {"name", "value"}


def test_ai_rule_is_draft_and_uses_supported_dsl() -> None:
    provider = MockProvider({RuleDraft: {"rule": {"name": "resolved_time_required", "type": "conditional_not_null", "status": "DRAFT", "condition": {"status": ["RESOLVED"]}, "column": "resolved_at"}}})
    draft = AIWorkflowService(provider).generate_rule("Resolved orders need time")
    assert draft.status == "DRAFT"
    assert draft.rule.type == "conditional_not_null"


def test_rca_refuses_when_evidence_is_insufficient() -> None:
    provider = MockProvider({AIRootCauseAnalysis: {"failure_class": "UNKNOWN", "probable_root_causes": [], "supporting_evidence": [], "recommended_checks": ["Collect diagnostic logs"], "confidence": 0.1, "insufficient_evidence": True}})
    assert AIWorkflowService(provider).analyze_rca({}).insufficient_evidence


def test_rca_rejects_unsupported_claims() -> None:
    with pytest.raises(ValidationError, match="supporting evidence"):
        AIRootCauseAnalysis(failure_class="OTA", probable_root_causes=["Bad package"], supporting_evidence=[], recommended_checks=[], confidence=0.8, insufficient_evidence=False)


def test_malformed_provider_output_fails_validation() -> None:
    with pytest.raises(ValidationError):
        AIWorkflowService(MockProvider({RequirementAnalysis: {"risks": []}})).analyze_requirement("anything")
