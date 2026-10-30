from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from automotive_quality.baselines.evidence_rca import analyze_evidence
from automotive_quality.baselines.template_test_generator import generate_template_tests
from automotive_quality.domains.ai.providers.openai import OpenAIProvider
from automotive_quality.domains.ai.schemas import AIRootCauseAnalysis, GeneratedTestSuite
from automotive_quality.domains.ai.workflows import AIWorkflowService
from automotive_quality.domains.evaluation.ai_value import (
    HumanTestDesignMeasurement,
    RCACase,
    RCAReview,
    RequirementCase,
    TestReview,
    aggregate,
    file_sha256,
    load_jsonl,
    rca_metrics,
    suggested_coverage,
    test_generation_metrics,
    write_json,
    write_jsonl,
)
from automotive_quality.domains.evaluation.policy import Policy, evaluate_policies

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the controlled AI-value benchmark without overwriting prior runs.")
    parser.add_argument("--experiment", choices=("test-generation", "rca"))
    parser.add_argument("--dataset")
    parser.add_argument("--provider", choices=("openai", "mock"), default="openai")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "gpt-5-mini"))
    parser.add_argument("--prompt-version", choices=("v2",), default="v2")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--api-max-retries", type=int, default=int(os.getenv("OPENAI_MAX_RETRIES", "5")),
        help="Retries for transient OpenAI connection, timeout, and server errors",
    )
    parser.add_argument(
        "--api-timeout-seconds", type=float, default=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "120")),
        help="Timeout for each OpenAI API attempt",
    )
    parser.add_argument("--reviews", help="Human-reviewed JSONL produced from the review queue")
    parser.add_argument("--human-baseline", help="Matched human-only test-design measurements in JSONL")
    parser.add_argument("--output-dir", default=str(ROOT / "results" / "ai_value"))
    parser.add_argument("--database-url", help="Optionally persist the immutable experiment summary and metrics")
    parser.add_argument("--policy", default=str(ROOT / "configs" / "ai_value_policies.yaml"))
    parser.add_argument("--allow-mock", action="store_true", help="Allow a regression-only dry run; never publish as AI-value evidence")
    parser.add_argument("--score-run", help="Score an existing immutable experiment directory without generating new model output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_config = None
    source_raw = None
    if args.score_run:
        source = Path(args.score_run)
        source_config = json.loads((source / "configuration.json").read_text(encoding="utf-8"))
        source_raw = json.loads((source / "raw_outputs.json").read_text(encoding="utf-8"))
        args.experiment = source_config["experiment"]
        args.dataset = source_config["dataset"]
        args.provider = source_config["provider"]
        args.model = source_config["model"]
        args.prompt_version = source_config["prompt_version"]
        args.runs = source_config["runs"]
    if not args.experiment or not args.dataset:
        raise SystemExit("--experiment and --dataset are required unless --score-run is supplied")
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    if args.api_max_retries < 0:
        raise SystemExit("--api-max-retries must be at least 0")
    if args.api_timeout_seconds <= 0:
        raise SystemExit("--api-timeout-seconds must be greater than 0")
    if args.provider == "mock" and not args.allow_mock:
        raise SystemExit("Mock output cannot prove AI value. Use OpenAI or explicitly pass --allow-mock for regression-only validation.")
    if args.provider == "openai" and not args.score_run and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required for a real AI-value experiment")

    dataset = Path(args.dataset)
    experiment_id = f"EXP-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8].upper()}"
    output = Path(args.output_dir) / experiment_id
    output.mkdir(parents=True, exist_ok=False)
    config = {
        "experiment_id": experiment_id,
        "experiment": args.experiment,
        "provider": args.provider,
        "model": args.model if args.provider == "openai" else "deterministic-regression-fixture",
        "prompt_version": args.prompt_version,
        "dataset": str(dataset),
        "dataset_sha256": file_sha256(dataset),
        "dataset_version": "ai-value-v1",
        "runs": args.runs,
        "api_max_retries": args.api_max_retries,
        "api_timeout_seconds": args.api_timeout_seconds,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "publishable": False,
        "source_experiment_id": source_config["experiment_id"] if source_config else None,
    }
    write_json(output / "configuration.json", config)

    if args.experiment == "test-generation":
        report, raw, review_queue = run_test_generation(args, source_raw)
    else:
        report, raw, review_queue = run_rca(args, source_raw)
    review_complete = report["review_completeness"]["complete"]
    baseline_complete = args.experiment == "rca" or report["human_baseline_completeness"]["complete"]
    config["publishable"] = bool(
        args.provider == "openai"
        and args.score_run
        and review_complete
        and baseline_complete
    )
    write_json(output / "configuration.json", config)
    report["experiment"] = config
    report["quality_gates"] = evaluate_quality_gates(report, args.experiment, args.policy, config["publishable"])
    report["conclusion"] = conclusion(report, config["publishable"])
    write_json(output / "raw_outputs.json", raw)
    write_jsonl(output / "review_queue.jsonl", review_queue)
    write_json(output / "report.json", report)
    if args.database_url:
        persist_experiment(args.database_url, config, raw, report)
    print(json.dumps({"experiment_id": experiment_id, "output": str(output), "publishable": config["publishable"], "conclusion": report["conclusion"]}, indent=2))


def run_test_generation(args: argparse.Namespace, source_raw: list[dict] | None = None) -> tuple[dict, list[dict], list[dict]]:
    cases = load_jsonl(args.dataset, RequirementCase)
    reviews = load_jsonl(args.reviews, TestReview) if args.reviews else []
    human_measurements = load_jsonl(args.human_baseline, HumanTestDesignMeasurement) if args.human_baseline else []
    review_index: dict[tuple[str, str, int], list[TestReview]] = {}
    for review in reviews:
        review_index.setdefault((review.variant, review.case_id, review.run_number), []).append(review)
    baseline_rows: list[dict[str, float]] = []
    ai_rows: list[dict[str, float]] = []
    raw: list[dict] = []
    queue: list[dict] = []
    service = AIWorkflowService(OpenAIProvider(
        args.model, max_retries=args.api_max_retries, timeout_seconds=args.api_timeout_seconds,
    )) if args.provider == "openai" and source_raw is None else None
    source_index = {(item["case_id"], item["run_number"]): item for item in source_raw or [] if item["variant"] in {"ai_assisted", "mock_regression"}}

    for benchmark in cases:
        baseline = generate_template_tests(benchmark.requirement)
        baseline_map = suggested_coverage(baseline, benchmark.gold)
        baseline_reviews = review_index.get(("deterministic_baseline", benchmark.requirement_id, 1), [])
        baseline_coverage = {item.test_id: item.validated_coverage for item in baseline_reviews} or baseline_map
        baseline_rows.append(test_generation_metrics(
            benchmark, baseline, baseline_coverage, baseline_reviews or None,
        ))
        raw.append({"variant": "deterministic_baseline", "case_id": benchmark.requirement_id, "run_number": 1, "output": baseline.model_dump(mode="json"), "coverage_mapping": baseline_map})
        for generated in baseline.cases:
            queue.append({
                "variant": "deterministic_baseline", "case_id": benchmark.requirement_id,
                "run_number": 1, "test_id": generated.test_id, "title": generated.title,
                "ai_claimed_coverage": [], "suggested_coverage": baseline_map[generated.test_id],
                "allowed_scenarios": [item.id for item in benchmark.gold.scenarios],
                "decision": None, "validated_coverage": [], "rejection_reasons": [],
                "active_review_seconds": None,
            })
        for run_number in range(1, args.runs + 1):
            generation_started = time.perf_counter()
            source_item = source_index.get((benchmark.requirement_id, run_number))
            if source_item:
                suite = GeneratedTestSuite.model_validate(source_item["output"])
                generation_seconds = float(source_item.get("generation_seconds", 0.0))
            elif service:
                analysis = service.analyze_requirement(benchmark.requirement)
                suite = service.generate_tests(benchmark.requirement, analysis, prompt_version=args.prompt_version)
                generation_seconds = time.perf_counter() - generation_started
            else:
                suite = generate_template_tests(benchmark.requirement)
                generation_seconds = time.perf_counter() - generation_started
            suggestions = suggested_coverage(suite, benchmark.gold)
            raw.append({"variant": "ai_assisted" if args.provider == "openai" else "mock_regression", "case_id": benchmark.requirement_id, "run_number": run_number, "generation_seconds": generation_seconds, "output": suite.model_dump(mode="json"), "suggested_coverage": suggestions})
            reviewed = review_index.get(("ai_assisted", benchmark.requirement_id, run_number))
            if reviewed:
                coverage = {item.test_id: item.validated_coverage for item in reviewed}
                row = test_generation_metrics(benchmark, suite, coverage, reviewed)
                row["generation_seconds"] = generation_seconds
                row["end_to_end_seconds"] = generation_seconds + row["active_review_seconds"]
                ai_rows.append(row)
            for generated in suite.cases:
                queue.append({
                    "variant": "ai_assisted", "case_id": benchmark.requirement_id,
                    "run_number": run_number, "test_id": generated.test_id,
                    "title": generated.title, "ai_claimed_coverage": generated.covers,
                    "suggested_coverage": suggestions[generated.test_id], "allowed_scenarios": [item.id for item in benchmark.gold.scenarios],
                    "decision": None, "validated_coverage": [], "rejection_reasons": [], "active_review_seconds": None,
                })
    human_rows = []
    benchmark_by_id = {item.requirement_id: item for item in cases}
    for measurement in human_measurements:
        benchmark = benchmark_by_id[measurement.case_id]
        allowed = {item.id for item in benchmark.gold.scenarios}
        human_rows.append({
            "requirement_coverage": len(set(measurement.validated_coverage) & allowed) / len(allowed),
            "active_design_seconds": measurement.active_design_seconds,
        })
    review_completeness = test_review_completeness(queue, reviews)
    human_completeness = human_baseline_completeness(cases, human_measurements)
    report = {
        "baseline": aggregate(baseline_rows), "human_only": aggregate(human_rows) if human_rows else None,
        "ai_assisted": aggregate(ai_rows) if ai_rows else None,
        "reviewed": review_completeness["complete"],
        "review_completeness": review_completeness,
        "human_baseline_completeness": human_completeness,
    }
    if ai_rows:
        report["difference_ai_minus_baseline"] = mean_differences(report["baseline"], report["ai_assisted"])
    if ai_rows and human_rows:
        human_time = report["human_only"]["active_design_seconds"]["mean"]
        ai_human_time = report["ai_assisted"]["active_review_seconds"]["mean"]
        ai_elapsed = report["ai_assisted"]["end_to_end_seconds"]["mean"]
        report["efficiency"] = {
            "human_effort_saving_rate": (human_time - ai_human_time) / human_time,
            "end_to_end_time_saving_rate": (human_time - ai_elapsed) / human_time,
        }
    return report, raw, queue


def run_rca(args: argparse.Namespace, source_raw: list[dict] | None = None) -> tuple[dict, list[dict], list[dict]]:
    cases = load_jsonl(args.dataset, RCACase)
    reviews = load_jsonl(args.reviews, RCAReview) if args.reviews else []
    review_index = {(item.case_id, item.run_number): item for item in reviews}
    baseline_rows: list[dict[str, float]] = []
    ai_rows: list[dict[str, float]] = []
    raw: list[dict] = []
    service = AIWorkflowService(OpenAIProvider(
        args.model, max_retries=args.api_max_retries, timeout_seconds=args.api_timeout_seconds,
    )) if args.provider == "openai" and source_raw is None else None
    source_index = {(item["case_id"], item["run_number"]): item for item in source_raw or [] if item["variant"] in {"ai_assisted", "mock_regression"}}
    for benchmark in cases:
        baseline = analyze_evidence(benchmark.evidence)
        baseline_row = rca_metrics(benchmark, baseline)
        baseline_review = review_index.get((benchmark.case_id, 1))
        if baseline_review:
            baseline_row["active_investigation_seconds"] = baseline_review.baseline_investigation_seconds
        baseline_rows.append(baseline_row)
        raw.append({"variant": "deterministic_baseline", "case_id": benchmark.case_id, "run_number": 1, "output": baseline.model_dump(mode="json")})
        for run_number in range(1, args.runs + 1):
            evidence = {"evidence_items": [item.model_dump() for item in benchmark.evidence]}
            source_item = source_index.get((benchmark.case_id, run_number))
            if source_item:
                result = AIRootCauseAnalysis.model_validate(source_item["output"])
            else:
                result = service.analyze_rca(evidence, prompt_version=args.prompt_version) if service else baseline
            row = rca_metrics(benchmark, result)
            review = review_index.get((benchmark.case_id, run_number))
            if review:
                row["recommended_check_usefulness"] = review.recommended_check_usefulness
                row["active_investigation_seconds"] = review.active_investigation_seconds
            ai_rows.append(row)
            raw.append({"variant": "ai_assisted" if args.provider == "openai" else "mock_regression", "case_id": benchmark.case_id, "run_number": run_number, "output": result.model_dump(mode="json")})
    queue = [{
        "case_id": benchmark.case_id, "run_number": run_number,
        "baseline_investigation_seconds": None, "recommended_check_usefulness": None,
        "active_investigation_seconds": None,
    } for benchmark in cases for run_number in range(1, args.runs + 1)]
    review_completeness = rca_review_completeness(queue, reviews)
    report = {
        "baseline": aggregate(baseline_rows), "ai_assisted": aggregate(ai_rows),
        "reviewed": review_completeness["complete"],
        "review_completeness": review_completeness,
    }
    report["difference_ai_minus_baseline"] = mean_differences(report["baseline"], report["ai_assisted"])
    return report, raw, queue


def test_review_completeness(queue: list[dict], reviews: list[TestReview]) -> dict:
    expected = {(item["variant"], item["case_id"], item["run_number"], item["test_id"]) for item in queue}
    actual = [(item.variant, item.case_id, item.run_number, item.test_id) for item in reviews]
    actual_set = set(actual)
    return completeness_summary(expected, actual, actual_set)


def rca_review_completeness(queue: list[dict], reviews: list[RCAReview]) -> dict:
    expected = {(item["case_id"], item["run_number"]) for item in queue}
    actual = [(item.case_id, item.run_number) for item in reviews]
    actual_set = set(actual)
    return completeness_summary(expected, actual, actual_set)


def human_baseline_completeness(
    cases: list[RequirementCase], measurements: list[HumanTestDesignMeasurement],
) -> dict:
    expected = {(item.requirement_id,) for item in cases}
    actual = [(item.case_id,) for item in measurements]
    return completeness_summary(expected, actual, set(actual))


def completeness_summary(expected: set[tuple], actual: list[tuple], actual_set: set[tuple]) -> dict:
    duplicates = len(actual) - len(actual_set)
    missing = expected - actual_set
    unexpected = actual_set - expected
    return {
        "complete": not missing and not unexpected and duplicates == 0,
        "expected_count": len(expected), "actual_count": len(actual),
        "missing_count": len(missing), "unexpected_count": len(unexpected),
        "duplicate_count": duplicates,
    }


def mean_differences(baseline: dict, ai: dict) -> dict[str, float]:
    return {name: ai[name]["mean"] - baseline[name]["mean"] for name in sorted(set(baseline) & set(ai))}


def conclusion(report: dict, publishable: bool) -> str:
    if not publishable:
        return "NOT PUBLISHABLE: real-provider output and completed human review are required before claiming AI improvement."
    return "Measured comparison complete. Interpret gains and regressions metric-by-metric; do not claim universal AI superiority."


def evaluate_quality_gates(report: dict, experiment: str, policy_path: str, publishable: bool) -> dict:
    if not publishable:
        return {"status": "NOT_EVALUATED", "reason": "Only publishable real-provider, human-reviewed runs may drive gates."}
    import yaml

    config = yaml.safe_load(Path(policy_path).read_text(encoding="utf-8"))
    metrics = {"ai": {name: values["mean"] for name, values in report["ai_assisted"].items()}}
    evaluations = evaluate_policies(metrics, [Policy.model_validate(item) for item in config["experiments"][experiment]])
    return {
        "status": "PASS" if all(item.passed for item in evaluations) else "BLOCK",
        "policy_status": config["status"],
        "evaluations": [item.model_dump() for item in evaluations],
    }


def persist_experiment(database_url: str, config: dict, raw: list[dict], report: dict) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from automotive_quality.infrastructure.database.repositories import EvaluationRunRepository

    metrics: dict[str, float] = {}
    for variant in ("baseline", "ai_assisted"):
        for name, summary in (report.get(variant) or {}).items():
            metrics[f"{variant}.{name}.mean"] = float(summary["mean"])
    with Session(create_engine(database_url, pool_pre_ping=True)) as session:
        EvaluationRunRepository(session).save(
            run_id=config["experiment_id"], dataset_name=config["experiment"], dataset_version=config["dataset_version"], metrics=metrics,
            experiment_group=config["experiment"], variant="comparison", baseline_type="deterministic",
            provider=config["provider"], model=config["model"], prompt_version=config["prompt_version"],
            dataset_hash=config["dataset_sha256"], run_number=config["runs"], configuration=config,
            raw_outputs=raw, summary=report,
        )
        session.commit()


if __name__ == "__main__":
    main()
