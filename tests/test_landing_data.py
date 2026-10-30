from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_landing_metrics_match_published_ai_value_artifacts() -> None:
    landing = json.loads((ROOT / "landing/public/project-metrics.json").read_text(encoding="utf-8"))
    test = json.loads((ROOT / "artifacts/ai_value/test_generation_report.json").read_text(encoding="utf-8"))
    rca = json.loads((ROOT / "artifacts/ai_value/rca_report.json").read_text(encoding="utf-8"))

    assert landing["testGeneration"]["gate"] == test["quality_gates"]["status"] == "BLOCK"
    assert landing["rca"]["gate"] == rca["quality_gates"]["status"] == "BLOCK"
    assert landing["testGeneration"]["aiCoverage"] == test["ai_assisted"]["requirement_coverage"]["mean"]
    assert landing["testGeneration"]["humanOnlyCoverage"] == test["human_only"]["requirement_coverage"]["mean"]
    assert landing["rca"]["rootCauseAccuracy"] == rca["ai_assisted"]["root_cause_accuracy"]["mean"]
