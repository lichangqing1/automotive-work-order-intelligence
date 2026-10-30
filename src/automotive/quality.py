from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pydantic import BaseModel


class Rule(BaseModel):
    name: str
    type: str
    column: str | None = None
    left: str | None = None
    right: str | None = None
    operator: str | None = None
    values: list[Any] | None = None
    condition_column: str | None = None
    condition_values: list[Any] | None = None
    where: str | None = None
    severity: str = "warning"


class RuleConfig(BaseModel):
    table: str
    rules: list[Rule]


@dataclass
class QualityResult:
    results: pd.DataFrame
    failed_row_indices: set[int]

    @property
    def passed(self) -> bool:
        return not bool(self.results.query("severity == 'critical' and failed_count > 0").shape[0])


def load_rules(path: str | Path) -> RuleConfig:
    with Path(path).open(encoding="utf-8") as handle:
        return RuleConfig.model_validate(yaml.safe_load(handle))


def evaluate_rules(df: pd.DataFrame, config: RuleConfig) -> QualityResult:
    records: list[dict[str, Any]] = []
    failed_rows: set[int] = set()
    for rule in config.rules:
        mask = pd.Series(False, index=df.index)
        if rule.type == "unique":
            mask = df[rule.column].duplicated(keep="first")
        elif rule.type == "not_null":
            mask = df[rule.column].isna()
        elif rule.type == "allowed_values":
            mask = ~df[rule.column].isin(rule.values)
        elif rule.type == "column_comparison":
            eligible = df[rule.left].notna() & df[rule.right].notna()
            if rule.operator == ">=":
                mask = eligible & ~(pd.to_datetime(df[rule.left]) >= pd.to_datetime(df[rule.right]))
            else:
                raise ValueError(f"Unsupported comparison operator: {rule.operator}")
        elif rule.type == "conditional_not_null":
            eligible = df[rule.condition_column].isin(rule.condition_values)
            mask = eligible & df[rule.column].isna()
        else:
            raise ValueError(f"Unsupported rule type: {rule.type}")
        indices = {int(i) for i in df.index[mask]}
        failed_rows.update(indices)
        records.append({
            "rule_name": rule.name,
            "rule_type": rule.type,
            "severity": rule.severity,
            "checked_count": len(df),
            "failed_count": int(mask.sum()),
            "pass_rate": round(1 - float(mask.mean()), 6),
            "status": "PASS" if not mask.any() else "FAIL",
        })
    return QualityResult(pd.DataFrame(records), failed_rows)
