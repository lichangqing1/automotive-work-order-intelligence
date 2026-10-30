from __future__ import annotations

import operator
from typing import Any

from pydantic import BaseModel

OPERATORS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt, "==": operator.eq, "!=": operator.ne}


class Policy(BaseModel):
    metric: str
    operator: str
    threshold: float


class PolicyEvaluation(BaseModel):
    metric: str
    actual: float
    operator: str
    threshold: float
    passed: bool


def _lookup(metrics: dict[str, Any], dotted_path: str) -> float:
    value: Any = metrics
    for part in dotted_path.split("."):
        value = value[part]
    return float(value)


def evaluate_policies(metrics: dict[str, Any], policies: list[Policy]) -> list[PolicyEvaluation]:
    evaluations = []
    for policy in policies:
        if policy.operator not in OPERATORS:
            raise ValueError(f"Unsupported policy operator: {policy.operator}")
        actual = _lookup(metrics, policy.metric)
        evaluations.append(PolicyEvaluation(
            metric=policy.metric, actual=actual, operator=policy.operator,
            threshold=policy.threshold, passed=OPERATORS[policy.operator](actual, policy.threshold),
        ))
    return evaluations

