from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

import pandas as pd

from .models import DQRule, DQRuleSet, QualityResult, RuleScope, RuleStatus


def _required_columns(rule: DQRule) -> set[str]:
    values = {rule.column, rule.left, rule.right, rule.condition_column, *rule.columns, *rule.condition.keys()}
    return {value for value in values if value}


def _condition_mask(df: pd.DataFrame, condition: Mapping[str, object]) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for column, expected in condition.items():
        accepted = expected if isinstance(expected, list) else [expected]
        mask &= df[column].isin(accepted)
    return mask


def evaluate_rules(
    df: pd.DataFrame,
    config: DQRuleSet,
    *,
    reference_tables: Mapping[str, pd.DataFrame] | None = None,
    now: datetime | None = None,
) -> QualityResult:
    records: list[dict[str, object]] = []
    failed_rows: set[int] = set()
    dataset_failures: list[str] = []
    configuration_errors: list[str] = []
    references = reference_tables or {}
    for rule in config.rules:
        if rule.status != RuleStatus.ACTIVE:
            continue
        missing = sorted(_required_columns(rule) - set(df.columns))
        if missing:
            error = f"MISSING_COLUMN: {', '.join(missing)}"
            configuration_errors.append(f"{rule.name}: {error}")
            records.append({"rule_name": rule.name, "rule_version": rule.version, "rule_type": rule.type, "scope": rule.scope, "severity": rule.severity, "checked_count": 0, "failed_count": 0, "pass_rate": 0.0, "status": "RULE_CONFIGURATION_ERROR", "error": error})
            continue
        mask = pd.Series(False, index=df.index)
        dataset_failed = False
        error = None
        if rule.type == "unique":
            mask = df[rule.column].duplicated(keep="first")
        elif rule.type == "not_null":
            mask = df[rule.column].isna()
        elif rule.type == "allowed_values":
            mask = ~df[rule.column].isin(rule.values)
        elif rule.type == "range":
            values = pd.to_numeric(df[rule.column], errors="coerce")
            mask = values.isna()
            if rule.min_value is not None:
                mask |= values < rule.min_value
            if rule.max_value is not None:
                mask |= values > rule.max_value
        elif rule.type == "regex":
            mask = ~df[rule.column].fillna("").astype(str).str.match(rule.pattern or r"$^")
        elif rule.type == "column_comparison":
            left = pd.to_datetime(df[rule.left], errors="coerce", utc=True)
            right = pd.to_datetime(df[rule.right], errors="coerce", utc=True)
            eligible = df[rule.left].notna() & df[rule.right].notna()
            malformed = eligible & (left.isna() | right.isna())
            comparisons = {">=": left >= right, ">": left > right, "<=": left <= right, "<": left < right, "==": left == right}
            mask = malformed | (eligible & ~comparisons[rule.operator])
        elif rule.type == "conditional_not_null":
            condition = rule.condition or {rule.condition_column: rule.condition_values}
            required = rule.columns or [rule.column]
            mask = _condition_mask(df, condition) & df[required].isna().any(axis=1)
        elif rule.type == "conditional_allowed_values":
            condition = rule.condition or {rule.condition_column: rule.condition_values}
            mask = _condition_mask(df, condition) & ~df[rule.column].isin(rule.values)
        elif rule.type == "foreign_key":
            reference = references.get(rule.reference_table or "")
            if reference is None:
                error = f"MISSING_REFERENCE_TABLE: {rule.reference_table}"
            elif rule.reference_column not in reference:
                error = f"MISSING_REFERENCE_COLUMN: {rule.reference_column}"
            else:
                mask = df[rule.column].notna() & ~df[rule.column].isin(reference[rule.reference_column])
        elif rule.type == "aggregate_reconciliation":
            actual = float(pd.to_numeric(df[rule.column], errors="coerce").sum()) if rule.column else float(len(df))
            dataset_failed = abs(actual - float(rule.expected)) > rule.tolerance
        elif rule.type == "freshness":
            timestamps = pd.to_datetime(df[rule.column], errors="coerce", utc=True)
            dataset_failed = timestamps.notna().sum() == 0 or ((now or datetime.now(timezone.utc)) - timestamps.max()).total_seconds() / 3600 > float(rule.max_value)
        if error:
            configuration_errors.append(f"{rule.name}: {error}")
        elif rule.scope == RuleScope.ROW:
            failed_rows.update(int(i) for i in df.index[mask])
        elif dataset_failed:
            dataset_failures.append(rule.name)
        failed_count = int(mask.sum()) if rule.scope == RuleScope.ROW else int(dataset_failed)
        status = "RULE_CONFIGURATION_ERROR" if error else ("FAIL" if failed_count else "PASS")
        records.append({"rule_name": rule.name, "rule_version": rule.version, "rule_type": rule.type, "scope": rule.scope, "severity": rule.severity, "checked_count": len(df), "failed_count": failed_count, "pass_rate": 0.0 if error else (1.0 if rule.scope == RuleScope.DATASET and not dataset_failed else round(1 - float(mask.mean()), 6)), "status": status, "error": error})
    return QualityResult(pd.DataFrame(records), failed_rows, dataset_failures, configuration_errors)
