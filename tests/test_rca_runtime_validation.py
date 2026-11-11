from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.domains.ai.providers.mock import MockProvider
from automotive_quality.domains.ai.schemas import AIRootCauseAnalysis
from automotive_quality.domains.ai.workflows import (
    AIWorkflowService,
    RCAEvidenceValidationError,
    RCAProviderFailure,
    RCAProviderOutputError,
)
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.database.repositories import AIRunRepository


def _evidence() -> dict[str, object]:
    return {
        "case_id": "CASE-1",
        "evidence_items": [
            {"id": "EV-1", "content": "Version 6.2 is unsupported.", "case_id": "CASE-1"},
            {"id": "EV-2", "content": "The failed vehicle attempted version 6.2.", "case_id": "CASE-1"},
        ],
    }


def _analysis(
    *,
    supporting: list[str] | None = None,
    claim_ids: list[str] | None = None,
    cause: str = "unsupported_software_version",
) -> dict[str, object]:
    supporting = ["EV-1"] if supporting is None else supporting
    claim_ids = ["EV-1"] if claim_ids is None else claim_ids
    return {
        "failure_class": "OTA_COMPATIBILITY",
        "probable_root_causes": [cause],
        "supporting_evidence": supporting,
        "recommended_checks": ["Verify the compatibility matrix"],
        "confidence": 0.8,
        "insufficient_evidence": False,
        "claims": [{"claim": cause, "evidence_ids": claim_ids}],
    }


def _service(output: dict[str, object]) -> AIWorkflowService:
    return AIWorkflowService(MockProvider({AIRootCauseAnalysis: output}))


def test_valid_evidence_references_are_accepted_for_human_review() -> None:
    result = _service(_analysis()).analyze_rca(_evidence())

    assert result.evidence_reference_status == "VALIDATED"
    assert result.review_status == "REVIEW_REQUIRED"
    assert result.supporting_evidence == ["EV-1"]


def test_fabricated_evidence_ids_are_provider_output_failures() -> None:
    with pytest.raises(RCAProviderOutputError) as raised:
        _service(_analysis(supporting=["EV-999"], claim_ids=["EV-999"])).analyze_rca(_evidence())

    assert raised.value.code == "INVALID_EVIDENCE_REFERENCES"
    assert all("Version 6.2" not in str(item) for item in raised.value.diagnostics)


@pytest.mark.parametrize("evidence_id", [None, "", "bad evidence id"])
def test_missing_or_malformed_request_evidence_ids_are_rejected_before_provider(
    evidence_id: str | None,
) -> None:
    item = {"content": "sensitive synthetic evidence"}
    if evidence_id is not None:
        item["id"] = evidence_id

    with pytest.raises(RCAEvidenceValidationError) as raised:
        _service(_analysis()).analyze_rca({"evidence_items": [item]})

    assert raised.value.code == "INVALID_RCA_EVIDENCE"
    assert "sensitive synthetic evidence" not in str(raised.value.diagnostics)


def test_duplicate_request_evidence_ids_are_rejected_before_provider() -> None:
    request = _evidence()
    request["evidence_items"] = [
        {"id": "EV-1", "content": "First fact"},
        {"id": "EV-1", "content": "Second fact"},
    ]

    with pytest.raises(RCAEvidenceValidationError, match="invalid"):
        _service(_analysis()).analyze_rca(request)


def test_duplicate_generated_citations_are_rejected_not_deduplicated() -> None:
    with pytest.raises(RCAProviderOutputError) as raised:
        _service(_analysis(
            supporting=["EV-1", "EV-1"],
            claim_ids=["EV-1", "EV-1"],
        )).analyze_rca(_evidence())

    assert raised.value.code == "INVALID_EVIDENCE_REFERENCES"
    assert any(item["issue"] == "duplicate_reference" for item in raised.value.diagnostics)


def test_evidence_from_another_case_is_rejected() -> None:
    request = _evidence()
    request["evidence_items"] = [
        {"id": "EV-1", "content": "Foreign fact", "case_id": "CASE-2"},
    ]

    with pytest.raises(RCAEvidenceValidationError) as raised:
        _service(_analysis()).analyze_rca(request)

    assert any(item["issue"] == "value_error" for item in raised.value.diagnostics)


def test_case_associated_evidence_requires_request_case_identity() -> None:
    with pytest.raises(RCAEvidenceValidationError):
        _service(_analysis()).analyze_rca({
            "evidence_items": [
                {"id": "EV-1", "content": "Scoped fact", "case_id": "CASE-1"},
            ],
        })


def test_empty_evidence_cannot_substantiate_asserted_root_cause() -> None:
    with pytest.raises(RCAProviderOutputError) as raised:
        _service(_analysis()).analyze_rca({})

    assert raised.value.code == "ASSERTION_WITHOUT_INPUT_EVIDENCE"


def test_root_cause_without_claim_level_support_is_rejected() -> None:
    output = _analysis()
    output["claims"] = []

    with pytest.raises(RCAProviderOutputError) as raised:
        _service(output).analyze_rca(_evidence())

    assert raised.value.code == "ROOT_CAUSE_WITHOUT_CLAIM_CITATION"


def test_valid_insufficient_evidence_abstention_is_accepted() -> None:
    output = {
        "failure_class": "INSUFFICIENT_EVIDENCE",
        "probable_root_causes": [],
        "supporting_evidence": [],
        "recommended_checks": ["Collect diagnostic logs"],
        "confidence": 0.1,
        "insufficient_evidence": True,
        "claims": [],
    }

    result = _service(output).analyze_rca({})

    assert result.insufficient_evidence is True
    assert result.evidence_reference_status == "INSUFFICIENT_EVIDENCE"
    assert result.review_status == "REVIEW_REQUIRED"


def test_malformed_provider_output_is_a_typed_provider_failure() -> None:
    service = _service({"failure_class": "OTA_COMPATIBILITY"})

    with pytest.raises(RCAProviderFailure) as raised:
        service.analyze_rca(_evidence())

    assert raised.value.code == "RCA_PROVIDER_FAILURE"
    assert raised.value.diagnostics == [{"failure_type": "ValidationError"}]


def test_provider_exception_is_a_typed_provider_failure() -> None:
    class FailingProvider:
        name = "fixture"
        model = "fixture"

        def generate_structured(self, *, prompt, response_model):
            del prompt, response_model
            raise RuntimeError("synthetic provider outage")

    with pytest.raises(RCAProviderFailure) as raised:
        AIWorkflowService(FailingProvider()).analyze_rca(_evidence())

    assert raised.value.code == "RCA_PROVIDER_FAILURE"
    assert raised.value.diagnostics == [{"failure_type": "RuntimeError"}]


def test_invalid_output_is_never_persisted_as_a_successful_ai_run() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = AIWorkflowService(
            MockProvider({
                AIRootCauseAnalysis: _analysis(
                    supporting=["EV-FABRICATED"],
                    claim_ids=["EV-FABRICATED"],
                ),
            }),
            AIRunRepository(session),
        )

        with pytest.raises(RCAProviderOutputError):
            service.analyze_rca(_evidence())

        record = session.scalar(select(models.AIRun).where(models.AIRun.task_type == "rca"))
        assert record is not None
        assert record.status == "FAILED"
        assert record.schema_valid is True
        assert record.output == {}
        assert "EV-FABRICATED" not in (record.error_message or "")
    engine.dispose()


def test_valid_output_retains_successful_audit_traceability() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service = AIWorkflowService(
            MockProvider({AIRootCauseAnalysis: _analysis()}),
            AIRunRepository(session),
        )

        result = service.analyze_rca(_evidence())
        record = session.get(models.AIRun, service.last_run_id)

        assert result.evidence_reference_status == "VALIDATED"
        assert record is not None
        assert record.status == "SUCCEEDED"
        assert record.output["evidence_reference_status"] == "VALIDATED"
        assert record.output["review_status"] == "REVIEW_REQUIRED"
    engine.dispose()


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def session_override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
            session.commit()

    previous = app.dependency_overrides.get(database_session)
    app.dependency_overrides[database_session] = session_override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        if previous is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous
        engine.dispose()


def test_api_sanitizes_invalid_evidence_errors(api_client: TestClient) -> None:
    response = api_client.post(
        "/api/v1/ai/rca/analyze",
        json={"evidence": {"evidence_items": [{"content": "sensitive synthetic content"}]}},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_RCA_EVIDENCE"
    assert "sensitive synthetic content" not in response.text


def test_api_returns_structured_provider_output_failure(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from automotive_quality.api import v1

    service = _service(_analysis(supporting=["EV-999"], claim_ids=["EV-999"]))
    monkeypatch.setattr(v1, "_ai_workflow", lambda session: service)

    response = api_client.post("/api/v1/ai/rca/analyze", json={"evidence": _evidence()})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "INVALID_EVIDENCE_REFERENCES"
    assert response.json()["detail"]["diagnostics"]
