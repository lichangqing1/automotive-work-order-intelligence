from sqlalchemy import create_engine, inspect

from automotive_quality.infrastructure.database import models  # noqa: F401
from automotive_quality.infrastructure.database.base import Base


def test_complete_schema_can_be_created_from_metadata() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"datasets", "dataset_versions", "ingestion_runs"} <= tables
    assert {"vehicles", "work_orders", "ota_releases", "diagnostic_events", "resolution_history"} <= tables
    assert {"dq_rules", "dq_rule_versions", "dq_runs", "dq_results"} <= tables
    assert {"test_cases", "test_runs", "test_results", "ai_runs", "evaluation_runs", "evaluation_metrics"} <= tables
    review_columns = {item["name"] for item in inspect(engine).get_columns("review_requests")}
    assert {"review_started_at", "active_review_seconds", "was_modified", "rejection_reasons", "validated_coverage"} <= review_columns
    evaluation_columns = {item["name"] for item in inspect(engine).get_columns("evaluation_runs")}
    assert {"experiment_group", "variant", "provider", "model", "dataset_hash", "configuration", "raw_outputs", "summary"} <= evaluation_columns


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
