from automotive_quality.domains.ai.evaluation import evaluate_ai_policies, evaluate_mock_baseline


def test_executable_ai_benchmark_and_policies() -> None:
    metrics = evaluate_mock_baseline("evaluation/datasets/ai_baseline.json")
    report = evaluate_ai_policies(metrics, "configs/ai_quality_policies.yaml")
    assert metrics["requirement"]["risk_coverage"] == 1.0
    assert metrics["rca"]["refusal_correctness"] == 1.0
    assert report["passed"]

