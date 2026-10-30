from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, model_validator


class RuleStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"


class RuleScope(StrEnum):
    ROW = "row"
    DATASET = "dataset"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DQRule(BaseModel):
    name: str
    type: str
    version: int = Field(default=1, ge=1)
    scope: RuleScope = RuleScope.ROW
    severity: Severity = Severity.WARNING
    status: RuleStatus = RuleStatus.ACTIVE
    column: str | None = None
    columns: list[str] = Field(default_factory=list)
    left: str | None = None
    right: str | None = None
    operator: str | None = None
    values: list[Any] | None = None
    min_value: float | None = None
    max_value: float | None = None
    pattern: str | None = None
    condition_column: str | None = None
    condition_values: list[Any] | None = None
    condition: dict[str, list[Any] | Any] = Field(default_factory=dict)
    reference_table: str | None = None
    reference_column: str | None = None
    expected: float | None = None
    tolerance: float = 0.0

    @model_validator(mode="after")
    def validate_supported_rule(self) -> DQRule:
        supported = {
            "unique", "not_null", "allowed_values", "column_comparison", "conditional_not_null",
            "foreign_key", "range", "regex", "conditional_allowed_values", "aggregate_reconciliation", "freshness",
        }
        if self.type not in supported:
            raise ValueError(f"Unsupported rule type: {self.type}")
        required: dict[str, tuple[str, ...]] = {
            "unique": ("column",), "not_null": ("column",), "allowed_values": ("column", "values"),
            "foreign_key": ("column", "reference_table", "reference_column"),
            "regex": ("column", "pattern"), "column_comparison": ("left", "operator", "right"),
            "conditional_allowed_values": ("column", "values"), "freshness": ("column", "max_value"),
        }
        missing = [field for field in required.get(self.type, ()) if getattr(self, field) is None]
        if self.type == "range" and (self.column is None or (self.min_value is None and self.max_value is None)):
            missing.append("column and min_value/max_value")
        if self.type == "conditional_not_null" and not (self.column or self.columns):
            missing.append("column/columns")
        if missing:
            raise ValueError(f"{self.type} missing required fields: {', '.join(missing)}")
        if self.type in {"aggregate_reconciliation", "freshness"} and self.scope != RuleScope.DATASET:
            raise ValueError(f"{self.type} must use dataset scope")
        return self


class DQRuleSet(BaseModel):
    table: str
    rules: list[DQRule]


@dataclass
class QualityResult:
    results: pd.DataFrame
    failed_row_indices: set[int]
    dataset_failures: list[str]
    configuration_errors: list[str]

    @property
    def passed(self) -> bool:
        failures = self.results.query("severity == 'critical' and status != 'PASS'")
        return failures.empty


class ManagedRule(BaseModel):
    rule_id: str
    name: str
    version: int
    status: RuleStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: datetime | None = None
    rule: DQRule

    def transition(self, target: RuleStatus) -> ManagedRule:
        allowed = {
            RuleStatus.DRAFT: RuleStatus.REVIEWED,
            RuleStatus.REVIEWED: RuleStatus.APPROVED,
            RuleStatus.APPROVED: RuleStatus.ACTIVE,
            RuleStatus.ACTIVE: RuleStatus.DEPRECATED,
        }
        if allowed.get(self.status) != target:
            raise ValueError(f"Invalid rule transition: {self.status} -> {target}")
        return self.model_copy(update={
            "status": target,
            "approved_at": datetime.now(timezone.utc) if target == RuleStatus.APPROVED else self.approved_at,
        })
