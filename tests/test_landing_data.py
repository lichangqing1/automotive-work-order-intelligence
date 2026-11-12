from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORTER_SPEC = importlib.util.spec_from_file_location(
    "export_landing_data", ROOT / "scripts/export_landing_data.py"
)
assert EXPORTER_SPEC is not None and EXPORTER_SPEC.loader is not None
EXPORTER = importlib.util.module_from_spec(EXPORTER_SPEC)
EXPORTER_SPEC.loader.exec_module(EXPORTER)
validate_rca_v2_provenance = EXPORTER.validate_rca_v2_provenance


def test_landing_metrics_match_published_ai_value_artifacts() -> None:
    landing = json.loads((ROOT / "landing/public/project-metrics.json").read_text(encoding="utf-8"))
    test = json.loads((ROOT / "artifacts/ai_value/test_generation_report.json").read_text(encoding="utf-8"))
    rca = json.loads((ROOT / "artifacts/ai_value/rca_report.json").read_text(encoding="utf-8"))
    rca_v2 = json.loads((ROOT / "docs/portfolio/data/rca_metrics_v2.json").read_text(encoding="utf-8"))

    assert landing["testGeneration"]["gate"] == test["quality_gates"]["status"] == "BLOCK"
    assert landing["rca"]["gate"] == rca["quality_gates"]["status"] == "BLOCK"
    assert landing["testGeneration"]["aiCoverage"] == test["ai_assisted"]["requirement_coverage"]["mean"]
    assert landing["testGeneration"]["humanOnlyCoverage"] == test["human_only"]["requirement_coverage"]["mean"]
    assert landing["rca"]["historicalV1"]["evidence_support_rate"] == rca["ai_assisted"]["evidence_support_rate"]["mean"]
    assert landing["rca"]["historicalV1"]["root_cause_accuracy"] == rca["ai_assisted"]["root_cause_accuracy"]["mean"]
    assert landing["rca"]["correctedV2"] == rca_v2["corrected_v2"]
    assert landing["rca"]["scoringVersion"] == "rca-metrics-v2"
    assert landing["rca"]["correctedV2"]["quality_gate"] == "BLOCK"


def _rca_records() -> tuple[dict, dict]:
    rca = json.loads((ROOT / "artifacts/ai_value/rca_report.json").read_text(encoding="utf-8"))
    rca_v2 = json.loads((ROOT / "docs/portfolio/data/rca_metrics_v2.json").read_text(encoding="utf-8"))
    return rca, rca_v2


def test_rca_v2_provenance_accepts_the_versioned_record() -> None:
    rca, rca_v2 = _rca_records()
    validate_rca_v2_provenance(rca, rca_v2)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("scoring_version",), "rca-metrics-unknown"),
        (("source_experiment_id",), "EXP-UNRELATED"),
        (("source_comparison_report",), "docs/reports/unreviewed.md"),
        (("historical_v1", "evidence_support_rate"), 0.0),
        (("historical_v1", "quality_gate"), "PASS"),
    ],
)
def test_rca_v2_provenance_rejects_mismatches(path: tuple[str, ...], replacement: object) -> None:
    rca, rca_v2 = _rca_records()
    changed = deepcopy(rca_v2)
    target = changed
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = replacement

    with pytest.raises(ValueError):
        validate_rca_v2_provenance(rca, changed)
