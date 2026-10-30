from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from automotive_quality.domains.evaluation.policy import Policy, evaluate_policies


def evaluate_quality_gates(metrics: dict[str, Any], config_path: str | Path) -> dict[str, Any]:
    """Compatibility adapter around the generic, metric-agnostic policy engine."""
    with Path(config_path).open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    policies = [Policy.model_validate(item) for item in config["policies"]]
    evaluations = evaluate_policies(metrics, policies)
    checks = {item.metric: item.passed for item in evaluations}
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "evaluations": [item.model_dump() for item in evaluations],
    }
