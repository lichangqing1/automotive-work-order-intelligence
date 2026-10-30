from pathlib import Path

from automotive.generator import generate_dataset
from automotive.processing import add_features, build_marts, clean_work_orders
from automotive.quality import evaluate_rules, load_rules

ROOT = Path(__file__).resolve().parents[1]


def test_injected_defects_are_detected() -> None:
    data = generate_dataset(rows=1000, seed=7, defect_rate=0.05)
    result = evaluate_rules(data.work_orders, load_rules(ROOT / "configs/data_quality_rules.yaml"))
    detection_rate = len(data.injected_defect_rows & result.failed_row_indices) / len(data.injected_defect_rows)
    assert detection_rate == 1.0
    assert not result.passed


def test_processing_and_marts() -> None:
    data = generate_dataset(rows=500, seed=10, defect_rate=0)
    clean = clean_work_orders(data.work_orders)
    features = add_features(clean, data.vehicles)
    marts = build_marts(features)
    assert len(features) == 500
    assert {"vehicle_age", "service_center_load", "same_version_issue_count"} <= set(features)
    assert set(marts) == {"daily_work_order_metrics", "ota_issue_summary", "vehicle_model_issue_summary", "team_resolution_performance"}
