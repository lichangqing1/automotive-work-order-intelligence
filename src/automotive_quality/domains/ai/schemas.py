from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from automotive_quality.domains.data_quality.models import DQRule, RuleStatus


class RequirementAnalysis(BaseModel):
    business_rules: list[str]
    risks: list[str]
    boundary_conditions: list[str]
    missing_information: list[str]
    recommended_test_scenarios: list[str]


class TestDataEntry(BaseModel):
    """One explicit test input accepted by OpenAI strict structured outputs."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: str | int | float | bool | None


class GeneratedTestCase(BaseModel):
    test_id: str
    title: str
    objective: str
    preconditions: list[str]
    test_data: list[TestDataEntry]
    steps: list[str]
    expected_result: str
    category: Literal["positive", "negative", "boundary", "exception", "data_quality", "integration"]
    priority: Literal["P0", "P1", "P2", "P3"]
    covers: list[str] = Field(default_factory=list)
    unsupported_assumptions: list[str] = Field(default_factory=list)
    review_status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"


class GeneratedTestSuite(BaseModel):
    requirement: str
    cases: list[GeneratedTestCase] = Field(min_length=1)


class RuleDraft(BaseModel):
    rule: DQRule
    status: Literal["DRAFT"] = "DRAFT"

    @model_validator(mode="after")
    def rule_must_be_draft(self) -> RuleDraft:
        if self.rule.status != RuleStatus.DRAFT:
            raise ValueError("AI-generated rules must use DRAFT status")
        return self

class RCAClaim(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(min_length=1)


class AIRootCauseAnalysis(BaseModel):
    failure_class: str
    probable_root_causes: list[str]
    supporting_evidence: list[str]
    recommended_checks: list[str]
    confidence: float = Field(ge=0, le=1)
    insufficient_evidence: bool
    claims: list[RCAClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_is_required_for_claims(self) -> AIRootCauseAnalysis:
        if self.probable_root_causes and not self.supporting_evidence:
            raise ValueError("Root-cause claims require supporting evidence")
        if self.insufficient_evidence and self.probable_root_causes:
            raise ValueError("Insufficient-evidence responses cannot claim root causes")
        if self.insufficient_evidence and self.claims:
            raise ValueError("Insufficient-evidence responses cannot contain claims")
        return self
