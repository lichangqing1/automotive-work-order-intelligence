from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from automotive_quality.domains.data_quality.models import DQRule, RuleStatus


class RequirementAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_rules: list[str] = Field(max_length=100)
    risks: list[str] = Field(max_length=100)
    boundary_conditions: list[str] = Field(max_length=100)
    missing_information: list[str] = Field(max_length=100)
    recommended_test_scenarios: list[str] = Field(max_length=100)

    @field_validator("business_rules", "risks", "boundary_conditions", "missing_information", "recommended_test_scenarios")
    @classmethod
    def analysis_items_are_bounded(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 4_000 for item in value):
            raise ValueError("analysis items must be non-blank and at most 4000 characters")
        return value


class TestDataEntry(BaseModel):
    """One explicit test input accepted by OpenAI strict structured outputs."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    value: str | int | float | bool | None

    @field_validator("value")
    @classmethod
    def string_value_is_bounded(cls, value: object) -> object:
        if isinstance(value, str) and len(value) > 4_000:
            raise ValueError("test-data string values are limited to 4000 characters")
        return value


class GeneratedTestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    objective: str = Field(min_length=1, max_length=4_000)
    preconditions: list[str] = Field(max_length=100)
    test_data: list[TestDataEntry] = Field(max_length=100)
    steps: list[str] = Field(min_length=1, max_length=100)
    expected_result: str = Field(min_length=1, max_length=8_000)
    category: Literal["positive", "negative", "boundary", "exception", "data_quality", "integration"]
    priority: Literal["P0", "P1", "P2", "P3"]
    covers: list[str] = Field(default_factory=list, max_length=100)
    unsupported_assumptions: list[str] = Field(default_factory=list, max_length=100)
    review_status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"

    @field_validator("preconditions", "steps", "covers", "unsupported_assumptions")
    @classmethod
    def generated_text_lists_are_bounded(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 4_000 for item in value):
            raise ValueError("generated test text items must be non-blank and bounded")
        return value


class GeneratedTestSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=1, max_length=12_000)
    cases: list[GeneratedTestCase] = Field(min_length=1, max_length=100)


class RuleDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    content: str = Field(min_length=1, max_length=8_000, validation_alias=AliasChoices("content", "fact"))
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
    evidence_items: list[RCAEvidenceItem] = Field(default_factory=list, max_length=100)

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
    model_config = ConfigDict(extra="forbid")

    claim: str = Field(min_length=1, max_length=4_000)
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=100)


class AIRootCauseAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_class: str = Field(min_length=1, max_length=128)
    probable_root_causes: list[str] = Field(max_length=100)
    # Legacy evaluation artifacts may contain descriptive text here. Runtime
    # validation still requires every value to be an authorized evidence ID.
    supporting_evidence: list[str] = Field(max_length=100)
    recommended_checks: list[str] = Field(max_length=100)
    confidence: float = Field(ge=0, le=1)
    insufficient_evidence: bool
    claims: list[RCAClaim] = Field(default_factory=list, max_length=100)
    evidence_reference_status: Literal["NOT_VALIDATED", "VALIDATED", "INSUFFICIENT_EVIDENCE"] = "NOT_VALIDATED"
    review_status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"

    @field_validator("probable_root_causes", "supporting_evidence", "recommended_checks")
    @classmethod
    def rca_text_lists_are_bounded(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 4_000 for item in value):
            raise ValueError("RCA text items must be non-blank and bounded")
        return value

    @model_validator(mode="after")
    def evidence_is_required_for_claims(self) -> AIRootCauseAnalysis:
        if self.probable_root_causes and not self.supporting_evidence:
            raise ValueError("Root-cause claims require supporting evidence")
        if self.insufficient_evidence and self.probable_root_causes:
            raise ValueError("Insufficient-evidence responses cannot claim root causes")
        if self.insufficient_evidence and self.claims:
            raise ValueError("Insufficient-evidence responses cannot contain claims")
        return self
