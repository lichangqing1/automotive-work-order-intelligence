from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mean(section: dict, key: str) -> float:
    return float(section[key]["mean"])


def main() -> None:
    artifacts = ROOT / "artifacts/ai_value"
    test = json.loads((artifacts / "test_generation_report.json").read_text(encoding="utf-8"))
    rca = json.loads((artifacts / "rca_report.json").read_text(encoding="utf-8"))
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
            "evidenceSupport": mean(rca["ai_assisted"], "evidence_support_rate"),
            "rootCauseAccuracy": mean(rca["ai_assisted"], "root_cause_accuracy"),
            "failureClassAccuracy": mean(rca["ai_assisted"], "failure_class_accuracy"),
        },
        "technology": ["Python", "FastAPI", "PostgreSQL", "SQL", "pytest", "Alembic", "OpenAI", "Jira REST API", "Streamlit", "Docker", "GitHub Actions"],
    }
    output = ROOT / "landing/public/project-metrics.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
