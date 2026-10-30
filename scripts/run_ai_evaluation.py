from __future__ import annotations

import json
from pathlib import Path

from automotive_quality.domains.ai.evaluation import evaluate_ai_policies, evaluate_mock_baseline

ROOT = Path(__file__).resolve().parents[1]


def main(root: Path = ROOT) -> None:
    metrics = evaluate_mock_baseline(root / "evaluation/datasets/ai_baseline.json")
    report = {"metrics": metrics, "quality_gates": evaluate_ai_policies(metrics, root / "configs/ai_quality_policies.yaml")}
    output = root / "results/automotive/ai_evaluation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["quality_gates"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
