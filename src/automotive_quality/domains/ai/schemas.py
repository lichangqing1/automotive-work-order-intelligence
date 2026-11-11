from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

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


EvidenceId = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class RCAEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: EvidenceId
    content: str = Field(min_length=1, validation_alias=AliasChoices("content", "fact"))
    case_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence content must not be blank")
        return value


class RCAEvidenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    evidence_items: list[RCAEvidenceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_ids_are_unambiguous_and_scoped(self) -> RCAEvidenceRequest:
        ids = [item.id for item in self.evidence_items]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evidence IDs are not allowed")
        associated_cases = {
            item.case_id for item in self.evidence_items if item.case_id is not None
        }
        if associated_cases and self.case_id is None:
            raise ValueError("request case ID is required for case-associated evidence")
        if self.case_id and any(
            item.case_id is not None and item.case_id != self.case_id
            for item in self.evidence_items
        ):
            raise ValueError("evidence item belongs to a different case")
        return self


class RCAClaim(BaseModel):
    claim: str
    evidence_ids: list[EvidenceId] = Field(min_length=1)


class AIRootCauseAnalysis(BaseModel):
    failure_class: str
    probable_root_causes: list[str]
    # Legacy evaluation artifacts may contain descriptive text here. Runtime
    # validation still requires every value to be an authorized evidence ID.
    supporting_evidence: list[str]
    recommended_checks: list[str]
    confidence: float = Field(ge=0, le=1)
    insufficient_evidence: bool
    claims: list[RCAClaim] = Field(default_factory=list)
    evidence_reference_status: Literal["NOT_VALIDATED", "VALIDATED", "INSUFFICIENT_EVIDENCE"] = "NOT_VALIDATED"
    review_status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"

    @model_validator(mode="after")
    def evidence_is_required_for_claims(self) -> AIRootCauseAnalysis:
        if self.probable_root_causes and not self.supporting_evidence:
            raise ValueError("Root-cause claims require supporting evidence")
        if self.insufficient_evidence and self.probable_root_causes:
            raise ValueError("Insufficient-evidence responses cannot claim root causes")
        if self.insufficient_evidence and self.claims:
            raise ValueError("Insufficient-evidence responses cannot contain claims")
        return self
