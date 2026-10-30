from automotive.ai import assist_resolution, build_rca, generate_rule
from automotive.evaluation import evaluate_rag_assistance
from automotive.gates import evaluate_quality_gates
from automotive.generator import generate_dataset
from automotive.models import WorkOrderInput
from automotive.retrieval import CaseIndex, evaluate_retrieval


def test_retrieval_and_grounded_assistance() -> None:
    frame = generate_dataset(rows=800, seed=42, defect_rate=0).work_orders
    index = CaseIndex.build(frame)
    case = WorkOrderInput(vehicle_model="Model-X", ota_version="6.2.1", description="screen black after software upgrade", error_code="IVI_E104")
    results = index.search("IVI_E104 central display black after OTA", top_k=5)
    assert results and results[0].category == "INFOTAINMENT"
    answer = assist_resolution(case, results)
    assert answer.citations == [result.work_order_id for result in results]
    assert answer.confidence > 0.5
    assert build_rca(case, results).supporting_evidence


def test_retrieval_regression_gate() -> None:
    index = CaseIndex.build(generate_dataset(rows=800, seed=4, defect_rate=0).work_orders)
    metrics = evaluate_retrieval(index, sample_size=30)
    assert metrics["hit_rate_at_5"] >= 0.70
    assert 0 <= metrics["recall_at_5"] <= 1
    assert 0 <= metrics["precision_at_5"] <= 1
    assert metrics["mrr"] >= 0.60


def test_rag_metrics_are_calculated_from_executed_cases() -> None:
    index = CaseIndex.build(generate_dataset(rows=500, seed=11, defect_rate=0).work_orders)
    metrics = evaluate_rag_assistance(index, sample_size=20)
    assert metrics == {"citation_validity": 1.0, "unsupported_claim_rate": 0.0}


def test_generated_rule_requires_human_approval() -> None:
    rule = generate_rule("Resolved OTA work orders must contain resolution information and resolved time")
    assert rule.status == "pending_approval"
    assert rule.condition == {"status": "RESOLVED", "service_type": "OTA"}
    assert {check["field"] for check in rule.checks} == {"resolution", "resolved_at"}


def test_quality_gate_evaluates_configured_thresholds() -> None:
    metrics = {
        "data_quality": {"critical_failed_rules": 0},
        "ml": {"roc_auc": 0.8, "f1": 0.7},
        "retrieval": {"hit_rate_at_5": 0.9, "recall_at_5": 0.1, "mrr": 0.85},
        "rag": {"citation_validity": 1.0, "unsupported_claim_rate": 0.0},
    }
    result = evaluate_quality_gates(metrics, "configs/quality_policies.yaml")
    assert result["passed"]
    assert all(result["checks"].values())
