from __future__ import annotations

import json
from pathlib import Path

from automotive_quality.domains.evaluation.ai_value import RCA_METRIC_VERSION

ROOT = Path(__file__).resolve().parents[1]
RCA_V2_SOURCE_REPORT = "artifacts/ai_value/rca_report.json"
RCA_V2_COMPARISON_REPORT = "docs/reports/RCA_METRIC_INTEGRITY_V2_COMPARISON.md"


def mean(section: dict, key: str) -> float:
    return float(section[key]["mean"])


def validate_rca_v2_provenance(rca: dict, rca_v2: dict) -> None:
    if rca_v2["scoring_version"] != RCA_METRIC_VERSION:
        raise ValueError("Corrected RCA scoring version is not supported by this exporter")
    if rca_v2["source_experiment_id"] != rca["experiment"]["experiment_id"]:
        raise ValueError("Corrected RCA metrics do not match the preserved source experiment")
    if rca_v2["source_historical_report"] != RCA_V2_SOURCE_REPORT:
        raise ValueError("Corrected RCA metrics name an unexpected historical report")
    if rca_v2["source_comparison_report"] != RCA_V2_COMPARISON_REPORT:
        raise ValueError("Corrected RCA metrics name an unexpected comparison report")
    if rca_v2["historical_v1"]["quality_gate"] != rca["quality_gates"]["status"]:
        raise ValueError("Corrected RCA provenance does not match the preserved policy decision")
    for metric in ("evidence_support_rate", "unsupported_claim_rate", "root_cause_accuracy"):
        if rca_v2["historical_v1"][metric] != mean(rca["ai_assisted"], metric):
            raise ValueError(f"Corrected RCA provenance does not match historical {metric}")


def main() -> None:
    artifacts = ROOT / "artifacts/ai_value"
    test = json.loads((artifacts / "test_generation_report.json").read_text(encoding="utf-8"))
    rca = json.loads((artifacts / "rca_report.json").read_text(encoding="utf-8"))
    rca_v2 = json.loads(
        (ROOT / "docs/portfolio/data/rca_metrics_v2.json").read_text(encoding="utf-8")
    )
    validate_rca_v2_provenance(rca, rca_v2)
    coverage = [
        ("Requirement coverage", "requirement_coverage"),
        ("Negative coverage", "negative_coverage"),
        ("Boundary coverage", "boundary_coverage"),
        ("Integration coverage", "integration_coverage"),
        ("Data-quality coverage", "data_quality_coverage"),
    ]
    payload = {
        "benchmark": {
            "workOrders": 30_000, "injectedDefects": 1_200, "detectedDefects": 1_200,
            "falseNegatives": 0, "falsePositives": 0, "aiEvaluationCases": 60,
            "checks": ["Completeness", "Validity", "Temporal consistency", "Cross-table integrity", "Reconciliation", "Business rules"],
        },
        "testGeneration": {
            "runs": test["experiment"]["runs"], "gate": test["quality_gates"]["status"],
            "coverage": [{"label": label, "baseline": mean(test["baseline"], key), "ai": mean(test["ai_assisted"], key)} for label, key in coverage],
            "humanEffortSaving": test["efficiency"]["human_effort_saving_rate"],
            "rejectionRate": mean(test["ai_assisted"], "rejection_rate"),
            "humanOnlyCoverage": mean(test["human_only"], "requirement_coverage"),
            "aiCoverage": mean(test["ai_assisted"], "requirement_coverage"),
        },
        "rca": {
            "runs": rca["experiment"]["runs"], "gate": rca["quality_gates"]["status"],
            "baselineSeconds": mean(rca["baseline"], "active_investigation_seconds"),
            "aiSeconds": mean(rca["ai_assisted"], "active_investigation_seconds"),
            "checkUsefulness": mean(rca["ai_assisted"], "recommended_check_usefulness"),
            "historicalV1": rca_v2["historical_v1"],
            "correctedV2": rca_v2["corrected_v2"],
            "scoringVersion": rca_v2["scoring_version"],
            "provenance": rca_v2["source_comparison_report"],
        },
        "technology": ["Python", "FastAPI", "PostgreSQL", "SQL", "pytest", "Alembic", "OpenAI", "Jira REST API", "Streamlit", "Docker", "GitHub Actions"],
    }
    output = ROOT / "landing/public/project-metrics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
