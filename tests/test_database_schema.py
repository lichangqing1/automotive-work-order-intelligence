from sqlalchemy import create_engine, inspect

from automotive_quality.infrastructure.database import models  # noqa: F401
from automotive_quality.infrastructure.database.base import Base


def test_complete_schema_can_be_created_from_metadata() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"datasets", "dataset_versions", "ingestion_runs", "ingestion_attempts"} <= tables
    assert {"vehicles", "work_orders", "ota_releases", "diagnostic_events", "resolution_history"} <= tables
    assert {"dq_rules", "dq_rule_versions", "dq_runs", "dq_results"} <= tables
    assert {
        "test_cases", "test_runs", "test_results", "ai_runs", "ai_operations",
        "evaluation_runs", "evaluation_metrics",
    } <= tables
    review_columns = {item["name"] for item in inspect(engine).get_columns("review_requests")}
    assert {
        "review_started_at", "active_review_seconds", "was_modified", "rejection_reasons",
        "validated_coverage", "ai_operation_id",
    } <= review_columns
    evaluation_columns = {item["name"] for item in inspect(engine).get_columns("evaluation_runs")}
    assert {"experiment_group", "variant", "provider", "model", "dataset_hash", "configuration", "raw_outputs", "summary"} <= evaluation_columns
    dataset_version_columns = {item["name"] for item in inspect(engine).get_columns("dataset_versions")}
    assert {"source_content_hash", "source_hash_version"} <= dataset_version_columns
    attempt_columns = {item["name"] for item in inspect(engine).get_columns("ingestion_attempts")}
    assert {"attempt_id", "dataset_version_reference", "status", "failure_stage", "error_category", "sanitized_error"} <= attempt_columns
    ai_run_columns = {item["name"] for item in inspect(engine).get_columns("ai_runs")}
    assert {"failure_stage", "error_category", "correlation_id", "completed_at"} <= ai_run_columns
    operation_columns = {item["name"] for item in inspect(engine).get_columns("ai_operations")}
    assert {
        "operation_id", "principal_id", "operation_type", "target_resource",
        "idempotency_key", "request_hash", "state", "owner_token", "response_payload",
        "ai_run_id", "error_category",
    } <= operation_columns
    operation_checks = {item["name"] for item in inspect(engine).get_check_constraints("ai_operations")}
    assert {
        "ck_ai_operations_state",
        "ck_ai_operations_terminal_timestamp",
        "ck_ai_operations_success_response",
    } <= operation_checks
    requirement_columns = {item["name"] for item in inspect(engine).get_columns("requirement_versions")}
    assert "created_by_principal_id" in requirement_columns
    test_case_version_columns = {item["name"] for item in inspect(engine).get_columns("test_case_versions")}
    assert "generated_by_principal_id" in test_case_version_columns
    test_run_columns = {item["name"] for item in inspect(engine).get_columns("test_runs")}
    assert "submitted_by_principal_id" in test_run_columns
    external_link_columns = {item["name"] for item in inspect(engine).get_columns("external_issue_links")}
    assert "last_retry_by_principal_id" in external_link_columns


def test_generator_output_ingests_through_source_boundary() -> None:
    from sqlalchemy.orm import Session

    from automotive_quality.domains.work_orders.ingestion import IngestionStatus, ingest_generated_dataset
    from automotive_quality.infrastructure.database.models import WorkOrder
    from automotive_quality.infrastructure.sources.synthetic import generate_dataset

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    data = generate_dataset(rows=100, seed=21, defect_rate=0)
    with Session(engine) as session:
        summary = ingest_generated_dataset(session, data, version="test-1")
        session.commit()
        assert summary.status == IngestionStatus.SUCCEEDED
        assert session.query(WorkOrder).count() == 100
