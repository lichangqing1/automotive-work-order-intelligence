from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "ai_value"
SOURCES = {
    "test_generation": ROOT / "results" / "ai_value" / "EXP-20261028T140042Z-D1B9B4C5" / "report.json",
    "rca": ROOT / "results" / "ai_value" / "EXP-20261029T132933Z-4731BD11" / "report.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sanitize(report: dict) -> dict:
    allowed = (
        "experiment",
        "conclusion",
        "reviewed",
        "review_completeness",
        "human_baseline_completeness",
        "baseline",
        "ai_assisted",
        "human_only",
        "difference_ai_minus_baseline",
        "efficiency",
        "quality_gates",
    )
    return {key: report[key] for key in allowed if key in report}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    published: dict[str, dict] = {}
    filenames = {
        "test_generation": "test_generation_report.json",
        "rca": "rca_report.json",
    }
    for name, source in SOURCES.items():
        report = json.loads(source.read_text(encoding="utf-8"))
        if report["experiment"]["provider"] != "openai":
            raise ValueError(f"{name} is not an OpenAI experiment")
        if report["experiment"]["runs"] != 3:
            raise ValueError(f"{name} does not contain three runs")
        if report["experiment"]["publishable"] is not True:
            raise ValueError(f"{name} is not publishable")
        if report["review_completeness"]["complete"] is not True:
            raise ValueError(f"{name} review is incomplete")
        if name == "test_generation" and report["human_baseline_completeness"]["complete"] is not True:
            raise ValueError("test-generation human baseline is incomplete")

        target = OUTPUT / filenames[name]
        target.write_text(json.dumps(sanitize(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        published[name] = {
            "experiment_id": report["experiment"]["experiment_id"],
            "experiment_type": report["experiment"]["experiment"],
            "provider": report["experiment"]["provider"],
            "model": report["experiment"]["model"],
            "prompt_version": report["experiment"]["prompt_version"],
            "dataset_version": report["experiment"]["dataset_version"],
            "dataset_sha256": report["experiment"]["dataset_sha256"],
            "runs": report["experiment"]["runs"],
            "publishable": report["experiment"]["publishable"],
            "quality_gate_status": report["quality_gates"]["status"],
            "source_report": str(source.relative_to(ROOT)),
            "source_report_sha256": sha256(source),
            "artifact": str(target.relative_to(ROOT)),
            "artifact_sha256": sha256(target),
        }

    readme = OUTPUT / "README.md"
    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": "ai-value-v1",
        "artifacts": published,
        "readme_sha256": sha256(readme),
        "sanitization": {
            "aggregate_metrics_only": True,
            "excluded": [
                "credentials",
                "environment files",
                "raw model outputs",
                "review workbooks",
                "individual review records",
                "reviewer identities",
            ],
        },
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(OUTPUT), "artifacts": published}, indent=2))


if __name__ == "__main__":
    main()
