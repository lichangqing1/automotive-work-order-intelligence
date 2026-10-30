from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.api.v1 import _issue_tracker
from automotive_quality.domains.work_orders.ingestion import ingest_generated_dataset
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.sources.synthetic import generate_dataset
from automotive_quality.integrations.issue_tracker import LocalIssueTracker

engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


Base.metadata.create_all(engine)
with Session(engine) as seed_session:
    ingest_generated_dataset(seed_session, generate_dataset(rows=200, seed=7, defect_rate=0), version="api-test")
    seed_session.commit()


def _session_override():
    with Session(engine) as session:
        yield session
        session.commit()


app.dependency_overrides[database_session] = _session_override
client = TestClient(app)


def test_liveness_contract() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_versioned_retrieval_contract() -> None:
    response = client.post("/api/v1/retrieval/search?top_k=2", json={
        "dataset_version": "api-test", "vehicle_model": "Model-X", "ota_version": "6.2.1",
        "description": "central display black after OTA", "error_code": "IVI_E104",
    })
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_unknown_test_run_returns_404() -> None:
    response = client.get("/api/v1/test-runs/TR-MISSING")
    assert response.status_code == 404


def test_overview_metrics_are_database_backed() -> None:
    response = client.get("/api/v1/metrics/overview")
    assert response.status_code == 200
    assert response.json()["total_work_orders"] == 200
    assert response.json()["ota_work_orders"] > 0


def test_requirement_analysis_contract() -> None:
    response = client.post("/api/v1/ai/requirements/analyze", json={"requirement": "Resolved OTA work orders need timestamps"})
    assert response.status_code == 200
    assert response.json()["risks"]


def test_all_structured_ai_workflows_are_exposed() -> None:
    analysis = client.post("/api/v1/ai/requirements/analyze", json={"requirement": "Resolved OTA orders need timestamps"}).json()
    tests = client.post("/api/v1/ai/tests/generate", json={"requirement": "Resolved OTA orders need timestamps", "analysis": analysis})
    rule = client.post("/api/v1/ai/dq-rules/generate", json={"requirement": "Resolved orders require resolved_at"})
    rca = client.post("/api/v1/ai/rca/analyze", json={"evidence": {}})
    assert tests.status_code == rule.status_code == rca.status_code == 200
    assert tests.json()["cases"][0]["review_status"] == "REVIEW_REQUIRED"
    assert rule.json()["rule"]["status"] == "DRAFT"
    assert rca.json()["insufficient_evidence"] is True


def test_legacy_ai_is_explicitly_a_baseline() -> None:
    payload = {"dataset_version": "api-test", "vehicle_model": "Model-X", "description": "display black", "error_code": "IVI_E104"}
    assert client.post("/api/v1/ai/rca", json=payload).status_code == 404
    assert client.post("/api/v1/baselines/ai/rca", json=payload).status_code == 200


def test_retrieval_never_manufactures_missing_data() -> None:
    response = client.post("/api/v1/retrieval/search", json={"dataset_version": "missing", "vehicle_model": "Model-X", "description": "display black"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "RETRIEVAL_INDEX_NOT_READY"


def test_dataset_version_is_the_public_data_identity() -> None:
    versions = client.get("/api/v1/datasets")
    detail = client.get("/api/v1/datasets/api-test")
    assert versions.status_code == detail.status_code == 200
    assert versions.json()[0]["version"] == "api-test"
    assert detail.json()["snapshot_count"] == 200


def test_ai_assisted_jira_review_execution_defect_and_traceability_workflow() -> None:
    imported = client.post("/api/v1/requirements/import/jira", json={"issue_key": "AUTO-103"})
    assert imported.status_code == 200
    requirement_version_id = imported.json()["requirement_version_id"]

    analysis = client.post(f"/api/v1/requirements/{requirement_version_id}/analyze")
    generated = client.post(f"/api/v1/requirements/{requirement_version_id}/generate-tests")
    assert analysis.status_code == generated.status_code == 200
    generation = generated.json()
    review_id = generation["review_id"]
    version_id = generation["test_case_version_ids"][0]

    blocked = client.post("/api/v1/test-runs", json={"requirement_version_id": requirement_version_id, "test_case_version_ids": [version_id], "dataset_version": "api-test"})
    assert blocked.status_code == 409

    tracker = _issue_tracker()
    assert isinstance(tracker, LocalIssueTracker)
    synced = client.post(f"/api/v1/reviews/{review_id}/decision", json={"status": "Approved", "reviewer": "qa.engineer", "comment": "Reviewed test intent and evidence"})
    assert synced.json()["status"] == "APPROVED"

    executed = client.post("/api/v1/test-runs", json={"requirement_version_id": requirement_version_id, "test_case_version_ids": [version_id], "dataset_version": "api-test", "actuals": {version_id: "Unexpected system behavior"}})
    assert executed.status_code == 200
    assert executed.json()["status"] == "FAILED"
    bug_keys = [key for key in tracker.issues if key.startswith("BUG-")]
    assert len(bug_keys) == 1

    duplicate = client.post("/api/v1/test-runs", json={"requirement_version_id": requirement_version_id, "test_case_version_ids": [version_id], "dataset_version": "api-test", "actuals": {version_id: "Unexpected system behavior"}})
    assert duplicate.status_code == 200
    assert [key for key in tracker.issues if key.startswith("BUG-")] == bug_keys

    trace = client.get(f"/api/v1/traceability/requirements/{requirement_version_id}")
    assert trace.status_code == 200
    assert trace.json()["test_case_versions"][0]["status"] == "APPROVED"
    assert any(item["artifact_type"] == "TEST_RESULT" for item in trace.json()["external_issues"])
    result = trace.json()["test_results"][0]
    assert result["test_case_version_id"] == version_id
    assert result["rca_ai_run_id"]
    assert trace.json()["rca_ai_runs"][0]["prompt_version"] == "v1"

    other = client.post("/api/v1/requirements/import/jira", json={"issue_key": "AUTO-OTHER"}).json()
    other_generation = client.post(f"/api/v1/requirements/{other['requirement_version_id']}/generate-tests").json()
    isolated_trace = client.get(f"/api/v1/traceability/requirements/{requirement_version_id}").json()
    assert other_generation["issue_key"] not in {item["issue_key"] for item in isolated_trace["external_issues"]}


def test_jira_outage_never_rolls_back_deterministic_failure(monkeypatch) -> None:
    requirement = client.post("/api/v1/requirements/import/jira", json={"issue_key": "AUTO-OUTAGE"}).json()
    requirement_id = requirement["requirement_version_id"]
    generation = client.post(f"/api/v1/requirements/{requirement_id}/generate-tests").json()
    version_id = generation["test_case_version_ids"][0]
    approved = client.post(f"/api/v1/reviews/{generation['review_id']}/decision", json={"status": "Approved", "reviewer": "qa.engineer"})
    assert approved.json()["status"] == "APPROVED"
    tracker = _issue_tracker()
    original_create_defect = tracker.create_defect

    def unavailable(**kwargs):
        del kwargs
        raise RuntimeError("Jira 503")

    monkeypatch.setattr(tracker, "create_defect", unavailable)
    execution = client.post("/api/v1/test-runs", json={"requirement_version_id": requirement_id, "test_case_version_ids": [version_id], "dataset_version": "api-test", "actuals": {version_id: "failure during outage"}})
    assert execution.status_code == 200
    assert execution.json()["status"] == "FAILED"
    assert execution.json()["external_sync"] == ["FAILED"]
    persisted = client.get(f"/api/v1/test-runs/{execution.json()['test_run_id']}")
    assert persisted.status_code == 200
    assert persisted.json()["results"][0]["status"] == "FAILED"
    trace = client.get(f"/api/v1/traceability/requirements/{requirement_id}").json()
    failed_link = next(item for item in trace["external_issues"] if item["artifact_type"] == "TEST_RESULT")
    assert failed_link["sync_status"] == "FAILED"
    monkeypatch.setattr(tracker, "create_defect", original_create_defect)
    retried = client.post(f"/api/v1/external-sync/{failed_link['link_id']}/retry")
    assert retried.status_code == 200
    assert retried.json()["sync_status"] == "SUCCEEDED"


def test_explicit_review_timing_and_coverage_assessment() -> None:
    requirement = client.post("/api/v1/requirements/import/jira", json={"issue_key": "AUTO-REVIEW-METRICS"}).json()
    generated = client.post(f"/api/v1/requirements/{requirement['requirement_version_id']}/generate-tests").json()
    review_id = generated["review_id"]
    version_id = generated["test_case_version_ids"][0]

    started = client.post(f"/api/v1/reviews/{review_id}/start")
    assessed = client.post(f"/api/v1/reviews/{review_id}/assessment", json={
        "was_modified": True,
        "validated_coverage": {version_id: ["missing_resolved_at"]},
        "rejection_reasons": [],
    })

    assert started.status_code == assessed.status_code == 200
    assert assessed.json()["active_review_seconds"] >= 0
    assert assessed.json()["was_modified"] is True
    assert assessed.json()["validated_coverage"][version_id] == ["missing_resolved_at"]


def test_ai_value_experiment_api_is_database_backed() -> None:
    response = client.get("/api/v1/ai-value/experiments")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
