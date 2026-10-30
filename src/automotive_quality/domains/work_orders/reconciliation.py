from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ReconciliationResult:
    name: str
    passed: bool
    expected: int | float
    actual: int | float
    variance: int | float


def reconcile_counts(raw_count: int, quarantined_count: int, clean_count: int) -> ReconciliationResult:
    expected = raw_count - quarantined_count
    return ReconciliationResult("raw_minus_quarantined_equals_clean", expected == clean_count, expected, clean_count, clean_count - expected)


def reconcile_grouped_metrics(
    expected: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    keys: list[str],
    metric: str,
    tolerance: float = 0,
) -> list[ReconciliationResult]:
    merged = expected[keys + [metric]].merge(actual[keys + [metric]], on=keys, how="outer", suffixes=("_expected", "_actual")).fillna(0)
    results: list[ReconciliationResult] = []
    for _, row in merged.iterrows():
        expected_value, actual_value = float(row[f"{metric}_expected"]), float(row[f"{metric}_actual"])
        label = ",".join(f"{key}={row[key]}" for key in keys)
        variance = actual_value - expected_value
        results.append(ReconciliationResult(f"{metric}[{label}]", abs(variance) <= tolerance, expected_value, actual_value, variance))
    return results

