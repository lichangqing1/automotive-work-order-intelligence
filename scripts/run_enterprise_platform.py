from __future__ import annotations

import argparse
import json
from pathlib import Path

from automotive_quality.application.runtime import PlatformRuntime, database_kpis
from automotive_quality.infrastructure.database.session import session_scope
from automotive_quality.infrastructure.sources.synthetic import generate_dataset

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PostgreSQL-backed enterprise platform path")
    parser.add_argument("--rows", type=int, default=30_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dataset-version", default="local-v1")
    args = parser.parse_args()
    data = generate_dataset(args.rows, args.seed)
    with session_scope() as session:
        summary = PlatformRuntime(session).execute(
            data, str(ROOT / "configs/enterprise_data_quality_rules.yaml"), dataset_version=args.dataset_version,
        )
        output = {
            "ingestion": summary.ingestion.__dict__, "dq_run_id": summary.dq_run_id,
            "source_quality_passed": summary.source_quality_passed,
            "defect_detection_passed": summary.defect_detection_passed,
            "publication_quality_passed": summary.publication_quality_passed,
            "final_gate_passed": summary.final_gate_passed,
            "defect_metrics": summary.defect_metrics.__dict__, "reconciliation": summary.reconciliation.__dict__,
            "sql_validations": summary.sql_validations,
            "database_kpis": database_kpis(session),
        }
        print(json.dumps(output, indent=2, default=str))
    if not summary.final_gate_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
