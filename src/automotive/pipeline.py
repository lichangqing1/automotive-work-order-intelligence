from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .evaluation import evaluate_rag_assistance
from .gates import evaluate_quality_gates
from .generator import generate_dataset, write_raw_data
from .ml import train_sla_predictor
from .models import PipelineSummary
from .processing import add_features, build_marts, clean_work_orders
from .quality import evaluate_rules, load_rules
from .retrieval import CaseIndex, evaluate_retrieval


def run_pipeline(root: str | Path, rows: int = 30_000, seed: int = 42) -> PipelineSummary:
    root = Path(root)
    raw_dir, processed_dir, result_dir = root / "data/raw", root / "data/processed", root / "results/automotive"
    processed_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)
    generated = generate_dataset(rows=rows, seed=seed)
    write_raw_data(generated, raw_dir)
    rules = load_rules(root / "configs/data_quality_rules.yaml")
    quality = evaluate_rules(generated.work_orders, rules)
    invalid = quality.failed_row_indices
    clean = clean_work_orders(generated.work_orders.drop(index=list(invalid)))
    publication_quality = evaluate_rules(clean, rules)
    features = add_features(clean, generated.vehicles)
    marts = build_marts(features)
    features.to_csv(processed_dir / "work_order_features.csv", index=False)
    quality.results.to_csv(result_dir / "data_quality_results.csv", index=False)
    db_path = root / "data/automotive_work_orders.sqlite"
    with sqlite3.connect(db_path) as connection:
        clean.to_sql("work_orders", connection, if_exists="replace", index=False)
        generated.vehicles.to_sql("vehicles", connection, if_exists="replace", index=False)
        generated.ota_releases.to_sql("ota_releases", connection, if_exists="replace", index=False)
        for name, frame in marts.items():
            frame.to_sql(name, connection, if_exists="replace", index=False)
    model_artifact = train_sla_predictor(features, seed=seed)
    case_index = CaseIndex.build(clean)
    retrieval_metrics = evaluate_retrieval(case_index)
    rag_metrics = evaluate_rag_assistance(case_index)
    critical_failures = int(publication_quality.results.query("severity == 'critical' and failed_count > 0").shape[0])
    metrics = {
        "data_quality": {"critical_failed_rules": critical_failures},
        "ml": model_artifact.metrics,
        "retrieval": retrieval_metrics,
        "rag": rag_metrics,
    }
    (result_dir / "evaluation_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    gates = evaluate_quality_gates(metrics, root / "configs/quality_policies.yaml")
    (result_dir / "quality_gates.json").write_text(json.dumps(gates, indent=2), encoding="utf-8")
    if not gates["passed"]:
        raise RuntimeError(f"Evaluation quality gates failed: {gates['checks']}")
    detected_injected = len(generated.injected_defect_rows & quality.failed_row_indices)
    summary = PipelineSummary(
        run_id=str(uuid.uuid4()), generated_at=datetime.now(timezone.utc), raw_rows=len(generated.work_orders),
        clean_rows=len(clean), injected_defects=len(generated.injected_defect_rows),
        detected_defect_rows=detected_injected,
        detection_rate=detected_injected / len(generated.injected_defect_rows), quality_passed=publication_quality.passed,
    )
    (result_dir / "pipeline_summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    return summary
