from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from automotive_quality.application.ai_testing_workflow import AITestingWorkflow, WorkflowConflict
from automotive_quality.application.runtime import database_kpis
from automotive_quality.baselines.deterministic_ai import assist_resolution, build_rca, generate_rule
from automotive_quality.baselines.schemas import DQRuleSpec, RCAResult, ResolutionResponse, WorkOrderInput
from automotive_quality.domains.ai.providers.mock import MockProvider
from automotive_quality.domains.ai.providers.openai import OpenAIProvider
from automotive_quality.domains.ai.schemas import (
    AIRootCauseAnalysis,
    GeneratedTestSuite,
    RCAEvidenceRequest,
    RequirementAnalysis,
    RuleDraft,
)
from automotive_quality.domains.ai.workflows import (
    AIWorkflowService,
    RCAEvidenceValidationError,
    RCAProviderError,
)
from automotive_quality.domains.retrieval.models import SimilarCase
from automotive_quality.domains.retrieval.service import RetrievalIndexNotReady, RetrievalService
from automotive_quality.domains.testing.models import TestRun
from automotive_quality.infrastructure.database import models as database_models
from automotive_quality.infrastructure.database.dataset_versions import (
    AmbiguousDatasetVersion,
    UnknownDatasetVersion,
    resolve_dataset_version,
)
from automotive_quality.infrastructure.database.repositories import AIRunRepository, PostgresTestRunRepository
from automotive_quality.integrations.issue_tracker import IssueTracker, LocalIssueTracker
from automotive_quality.integrations.jira import JiraIssueTracker
from automotive_quality.shared.config import get_settings

from .auth import AuthenticatedPrincipal, authenticated_principal
from .authorization import Permission
from .dependencies import database_session, retrieval_service
from .rate_limits import OperationCategory, enforce_rate_limit, ensure_ai_concurrency_protected

router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticated_principal)])
DatabaseSession = Annotated[Session, Depends(database_session)]
Retrieval = Annotated[RetrievalService, Depends(retrieval_service)]
Reader = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.READ, OperationCategory.READ)),
]
BaselineAIController = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.OPERATE_AI, OperationCategory.AI)),
]
AIController = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.OPERATE_AI, OperationCategory.AI, ai_concurrency=True)),
]
RequirementAIController = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.OPERATE_REQUIREMENTS, OperationCategory.AI, ai_concurrency=True)),
]
JiraRequirementOperator = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.OPERATE_REQUIREMENTS, OperationCategory.JIRA)),
]
TestSubmitter = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.SUBMIT_TEST_RESULTS, OperationCategory.MUTATION)),
]
Reviewer = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.REVIEW, OperationCategory.MUTATION)),
]
JiraReviewer = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.REVIEW, OperationCategory.JIRA)),
]
SyncOperator = Annotated[
    AuthenticatedPrincipal,
    Depends(enforce_rate_limit(Permission.RETRY_EXTERNAL_SYNC, OperationCategory.JIRA)),
]


class RequirementRequest(BaseModel):
    requirement: str


class TestGenerationRequest(BaseModel):
    requirement: str
    analysis: RequirementAnalysis


class RCARequest(BaseModel):
    evidence: RCAEvidenceRequest | dict[str, object]


class RetrievalRequest(WorkOrderInput):
    dataset_version: str


class JiraImportRequest(BaseModel):
    issue_key: str


class TestRunRequest(BaseModel):
    requirement_version_id: str
    test_case_version_ids: list[str]
    dataset_version: str
    actuals: dict[str, str] = Field(default_factory=dict)


class TestRunResponse(BaseModel):
    test_run_id: str
    status: str
    execution_mode: str
    automatically_executed: bool
    submitted_results: int
    passed: int
    failed: int
    total: int
    external_sync: list[str]


class ReviewDecisionRequest(BaseModel):
    status: str
    reviewer: str | None = None
    comment: str | None = None


class ReviewAssessmentRequest(BaseModel):
    was_modified: bool
    validated_coverage: dict[str, list[str]]
    rejection_reasons: list[str] = []


@lru_cache(maxsize=1)
def _issue_tracker() -> IssueTracker:
    settings = get_settings()
    if settings.issue_tracker == "local":
        return LocalIssueTracker()
    if settings.issue_tracker == "jira" and settings.jira_base_url and settings.jira_email and settings.jira_api_token:
        return JiraIssueTracker(settings.jira_base_url, settings.jira_email, settings.jira_api_token, settings.jira_project_key, settings.jira_review_issue_type, settings.jira_bug_issue_type)
    raise RuntimeError("Jira issue tracker is enabled but credentials are incomplete")


def _testing_workflow(session: Session) -> AITestingWorkflow:
    settings = get_settings()
    return AITestingWorkflow(session, _ai_workflow(session), _issue_tracker(), set(settings.jira_approved_statuses.split(",")), set(settings.jira_rejected_statuses.split(",")))


def _ai_workflow(session: Session) -> AIWorkflowService:
    settings = get_settings()
    if settings.llm_provider == "openai":
        provider = OpenAIProvider(settings.llm_model, settings.openai_api_key)
    elif settings.llm_provider == "mock":
        provider = MockProvider({
            RequirementAnalysis: {
                "business_rules": ["Resolved OTA work orders require supported versions and resolution timestamps"],
                "risks": ["Unsupported OTA release", "Missing closure evidence"],
                "boundary_conditions": ["First supported OTA version", "Closed order without resolved timestamp"],
                "missing_information": ["Compatibility matrix approval source"],
                "recommended_test_scenarios": ["Reject unsupported OTA version", "Require resolution timestamp"],
            },
            GeneratedTestSuite: {
                "requirement": "Resolved OTA work orders require supported versions and timestamps",
                "cases": [{"test_id": "AI-TC-001", "title": "Reject missing resolution timestamp", "objective": "Verify closure evidence", "preconditions": ["OTA work order exists"], "test_data": [{"name": "status", "value": "RESOLVED"}, {"name": "resolved_at", "value": None}], "steps": ["Submit the work order"], "expected_result": "The deterministic quality gate rejects the row", "category": "negative", "priority": "P1"}],
            },
            RuleDraft: {"rule": {"name": "resolved_timestamp_required", "type": "conditional_not_null", "status": "DRAFT", "severity": "critical", "condition": {"status": ["RESOLVED", "CLOSED"]}, "columns": ["resolved_at"]}},
            AIRootCauseAnalysis: {"failure_class": "INSUFFICIENT_EVIDENCE", "probable_root_causes": [], "supporting_evidence": [], "recommended_checks": ["Collect diagnostic events and release compatibility evidence"], "confidence": 0.1, "insufficient_evidence": True},
        })
    else:
        raise HTTPException(status_code=503, detail=f"Unsupported LLM provider: {settings.llm_provider}")
    return AIWorkflowService(provider, AIRunRepository(session))


def _query(case: WorkOrderInput) -> str:
    return " ".join(filter(None, [case.error_code, case.description, case.ota_version]))


def _bind_reviewer(
    session: Session,
    review_id: str,
    principal: AuthenticatedPrincipal,
    *,
    claimed_reviewer: str | None = None,
) -> database_models.ReviewRequest:
    review = session.scalar(
        select(database_models.ReviewRequest)
        .where(database_models.ReviewRequest.review_id == review_id)
        .with_for_update()
    )
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    if claimed_reviewer is not None and claimed_reviewer != principal.principal_id:
        raise HTTPException(status_code=409, detail="Reviewer identity must match the authenticated principal")
    if review.reviewer is not None and review.reviewer != principal.principal_id:
        raise HTTPException(status_code=403, detail="Review is assigned to a different authenticated principal")
    versions = [session.get(database_models.TestCaseVersion, artifact_id) for artifact_id in review.artifact_ids]
    if review.artifact_type != "TEST_CASE_BATCH" or not versions or any(version is None for version in versions):
        raise HTTPException(status_code=409, detail="Review artifact relationships are invalid")
    typed_versions = [version for version in versions if version is not None]
    requirement_ids = {version.requirement_version_id for version in typed_versions}
    if len(requirement_ids) != 1:
        raise HTTPException(status_code=409, detail="Review artifacts must belong to one requirement version")
    is_administrator = "administrator" in principal.roles
    generators = {version.generated_by_principal_id for version in typed_versions}
    if None in generators and not is_administrator:
        raise HTTPException(status_code=403, detail="Unattributed historical reviews require an administrator")
    if principal.principal_id in generators and not is_administrator:
        raise HTTPException(status_code=403, detail="A principal cannot review its own generated output")
    review.reviewer = principal.principal_id
    session.flush()
    return review


@router.post("/retrieval/search", response_model=list[SimilarCase])
def search(case: RetrievalRequest, _principal: Reader, service: Retrieval, top_k: int = Query(5, ge=1, le=20)) -> list[SimilarCase]:
    try:
        return service.search(case.dataset_version, _query(case), top_k=top_k)
    except RetrievalIndexNotReady as exc:
        raise HTTPException(status_code=503, detail={"code": "RETRIEVAL_INDEX_NOT_READY", "message": str(exc)}) from exc


@router.post("/baselines/ai/resolution", response_model=ResolutionResponse)
def resolution(case: RetrievalRequest, _principal: BaselineAIController, service: Retrieval, top_k: int = Query(5, ge=1, le=20)) -> ResolutionResponse:
    try:
        similar = service.search(case.dataset_version, _query(case), top_k=top_k)
    except RetrievalIndexNotReady as exc:
        raise HTTPException(status_code=503, detail={"code": "RETRIEVAL_INDEX_NOT_READY", "message": str(exc)}) from exc
    return assist_resolution(case, similar)


@router.post("/baselines/ai/rca", response_model=RCAResult)
def rca(case: RetrievalRequest, _principal: BaselineAIController, service: Retrieval, top_k: int = Query(5, ge=1, le=20)) -> RCAResult:
    try:
        similar = service.search(case.dataset_version, _query(case), top_k=top_k)
    except RetrievalIndexNotReady as exc:
        raise HTTPException(status_code=503, detail={"code": "RETRIEVAL_INDEX_NOT_READY", "message": str(exc)}) from exc
    return build_rca(case, similar)


@router.post("/baselines/dq/rules/draft", response_model=DQRuleSpec)
def draft_rule(_principal: BaselineAIController, requirement: str = Query(min_length=5)) -> DQRuleSpec:
    return generate_rule(requirement)


@router.get("/test-runs", response_model=list[TestRun])
def list_test_runs(_principal: Reader, session: DatabaseSession) -> list[TestRun]:
    return PostgresTestRunRepository(session).list()


@router.get("/test-runs/{run_id}", response_model=TestRun)
def get_test_run(run_id: str, _principal: Reader, session: DatabaseSession) -> TestRun:
    run = PostgresTestRunRepository(session).get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return run


@router.get("/metrics/overview")
def overview(_principal: Reader, session: DatabaseSession, dataset_version: str | None = None) -> dict[str, object]:
    try:
        return database_kpis(session, dataset_version)
    except UnknownDatasetVersion as exc:
        raise HTTPException(status_code=404, detail="Dataset version not found") from exc
    except AmbiguousDatasetVersion as exc:
        raise HTTPException(status_code=409, detail="Dataset version label is ambiguous; use dataset_version_id") from exc


@router.get("/datasets")
def list_datasets(_principal: Reader, session: DatabaseSession) -> list[dict[str, object]]:
    versions = session.scalars(select(database_models.DatasetVersion).order_by(database_models.DatasetVersion.created_at.desc())).all()
    return [{"dataset_version_id": item.dataset_version_id, "dataset_id": item.dataset_id, "version": item.version, "row_count": item.row_count, "content_hash": item.content_hash, "created_at": item.created_at} for item in versions]


@router.get("/datasets/{version}")
def get_dataset(version: str, _principal: Reader, session: DatabaseSession) -> dict[str, object]:
    try:
        item = resolve_dataset_version(session, version)
    except UnknownDatasetVersion:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    except AmbiguousDatasetVersion as exc:
        raise HTTPException(status_code=409, detail="Dataset version label is ambiguous; use dataset_version_id") from exc
    snapshot_count = len(session.scalars(select(database_models.WorkOrderSnapshot.snapshot_id).where(database_models.WorkOrderSnapshot.dataset_version_id == item.dataset_version_id)).all())
    ingestion_runs = session.scalars(select(database_models.IngestionRun).where(
        database_models.IngestionRun.dataset_version_id == item.dataset_version_id
    )).all()
    if len(ingestion_runs) > 1:
        raise HTTPException(status_code=409, detail="Dataset version has multiple ingestion runs")
    ingestion = ingestion_runs[0] if ingestion_runs else None
    attempts = session.scalars(select(database_models.IngestionAttempt).where(
        database_models.IngestionAttempt.dataset_version_id == item.dataset_version_id
    ).order_by(database_models.IngestionAttempt.started_at)).all()
    quarantined = ingestion.rejected_rows if ingestion else 0
    source_count = (ingestion.ingested_rows + quarantined) if ingestion else item.row_count
    return {"dataset_version_id": item.dataset_version_id, "dataset_id": item.dataset_id, "version": item.version, "row_count": item.row_count, "source_row_count": source_count, "clean_row_count": snapshot_count, "quarantined_row_count": quarantined, "snapshot_count": snapshot_count, "content_hash": item.content_hash, "source_hash_version": item.source_hash_version, "ingestion_status": ingestion.status if ingestion else None, "ingestion_attempt_count": len(attempts), "last_ingestion_attempt_status": attempts[-1].status if attempts else None, "created_at": item.created_at}


@router.post("/ai/requirements/analyze", response_model=RequirementAnalysis)
def analyze_requirement(request: RequirementRequest, principal: AIController, session: DatabaseSession) -> RequirementAnalysis:
    result = _ai_workflow(session).analyze_requirement(request.requirement)
    ensure_ai_concurrency_protected(principal)
    return result


@router.post("/ai/tests/generate", response_model=GeneratedTestSuite)
def generate_tests(request: TestGenerationRequest, principal: AIController, session: DatabaseSession) -> GeneratedTestSuite:
    result = _ai_workflow(session).generate_tests(request.requirement, request.analysis)
    ensure_ai_concurrency_protected(principal)
    return result


@router.post("/ai/dq-rules/generate", response_model=RuleDraft)
def generate_dq_rule(request: RequirementRequest, principal: AIController, session: DatabaseSession) -> RuleDraft:
    result = _ai_workflow(session).generate_rule(request.requirement)
    ensure_ai_concurrency_protected(principal)
    return result


@router.post("/ai/rca/analyze", response_model=AIRootCauseAnalysis)
def analyze_root_cause(request: RCARequest, principal: AIController, session: DatabaseSession) -> AIRootCauseAnalysis:
    try:
        result = _ai_workflow(session).analyze_rca(request.evidence)
    except RCAEvidenceValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": str(exc), "diagnostics": exc.diagnostics},
        ) from exc
    except RCAProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": exc.code, "message": str(exc), "diagnostics": exc.diagnostics},
        ) from exc
    ensure_ai_concurrency_protected(principal)
    return result


@router.post("/requirements/import/jira")
def import_jira_requirement(request: JiraImportRequest, principal: JiraRequirementOperator, session: DatabaseSession) -> dict[str, object]:
    record = _testing_workflow(session).import_requirement(request.issue_key, actor_principal_id=principal.principal_id)
    return {"requirement_version_id": record.requirement_version_id, "requirement_id": record.requirement_id, "version": record.version, "external_reference": record.external_reference}


@router.post("/requirements/{requirement_version_id}/analyze")
def analyze_persisted_requirement(requirement_version_id: str, principal: RequirementAIController, session: DatabaseSession) -> dict:
    try:
        result = _testing_workflow(session).analyze(requirement_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Requirement version not found") from exc
    ensure_ai_concurrency_protected(principal)
    return result


@router.post("/requirements/{requirement_version_id}/generate-tests")
def generate_persisted_tests(requirement_version_id: str, principal: RequirementAIController, session: DatabaseSession) -> dict:
    try:
        result = _testing_workflow(session).generate_tests(
            requirement_version_id,
            actor_principal_id=principal.principal_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Requirement version not found") from exc
    except WorkflowConflict as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ensure_ai_concurrency_protected(principal)
    return result


@router.get("/reviews/{review_id}")
def get_review(review_id: str, _principal: Reader, session: DatabaseSession) -> dict[str, object]:
    review = session.get(database_models.ReviewRequest, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")
    link = session.scalar(select(database_models.ExternalIssueLink).where(database_models.ExternalIssueLink.artifact_type == "REVIEW", database_models.ExternalIssueLink.artifact_id == review_id))
    return {"review_id": review.review_id, "status": review.status, "artifact_ids": review.artifact_ids, "external_reference": link.issue_key if link else None}


@router.post("/reviews/{review_id}/sync")
def sync_review(review_id: str, principal: JiraReviewer, session: DatabaseSession) -> dict[str, object]:
    try:
        _bind_reviewer(session, review_id, principal)
        review = _testing_workflow(session).sync_review(review_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Review not found") from exc
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"review_id": review.review_id, "status": review.status, "artifact_ids": review.artifact_ids}


@router.post("/reviews/{review_id}/start")
def start_review(review_id: str, principal: Reviewer, session: DatabaseSession) -> dict[str, object]:
    review = _bind_reviewer(session, review_id, principal)
    review.review_started_at = datetime.now(timezone.utc)
    review.active_review_seconds = None
    session.flush()
    return {"review_id": review.review_id, "review_started_at": review.review_started_at}


@router.post("/reviews/{review_id}/assessment")
def complete_review_assessment(review_id: str, request: ReviewAssessmentRequest, principal: Reviewer, session: DatabaseSession) -> dict[str, object]:
    review = _bind_reviewer(session, review_id, principal)
    if review.review_started_at is None:
        raise HTTPException(status_code=409, detail="Review timing has not been started")
    completed_at = datetime.now(timezone.utc)
    started_at = review.review_started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    review.completed_at = completed_at
    review.active_review_seconds = max(0.0, (completed_at - started_at).total_seconds())
    review.was_modified = request.was_modified
    review.validated_coverage = request.validated_coverage
    review.rejection_reasons = request.rejection_reasons
    session.flush()
    return {
        "review_id": review.review_id, "active_review_seconds": review.active_review_seconds,
        "was_modified": review.was_modified, "validated_coverage": review.validated_coverage,
        "rejection_reasons": review.rejection_reasons,
    }


@router.post("/reviews/{review_id}/decision")
def decide_local_review(review_id: str, request: ReviewDecisionRequest, principal: Reviewer, session: DatabaseSession) -> dict[str, object]:
    review = _bind_reviewer(session, review_id, principal, claimed_reviewer=request.reviewer)
    tracker = _issue_tracker()
    if not isinstance(tracker, LocalIssueTracker):
        raise HTTPException(status_code=409, detail="Review decisions must be made in the configured external issue tracker")
    link = session.scalar(select(database_models.ExternalIssueLink).where(database_models.ExternalIssueLink.artifact_type == "REVIEW", database_models.ExternalIssueLink.artifact_id == review_id))
    if link is None:
        raise HTTPException(status_code=409, detail="Review has no issue link")
    tracker.set_issue_status(link.issue_key, request.status)
    review.review_comment = request.comment
    synced = _testing_workflow(session).sync_review(review_id)
    return {"review_id": synced.review_id, "status": synced.status, "artifact_ids": synced.artifact_ids}


@router.post("/test-runs", response_model=TestRunResponse)
def launch_test_run(request: TestRunRequest, principal: TestSubmitter, session: DatabaseSession) -> dict:
    """Validate complete caller-submitted results; this does not execute test steps."""
    try:
        return _testing_workflow(session).execute(
            request.requirement_version_id,
            request.test_case_version_ids,
            request.actuals,
            request.dataset_version,
            actor_principal_id=principal.principal_id,
        )
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/traceability/requirements/{requirement_version_id}")
def requirement_traceability(requirement_version_id: str, _principal: Reader, session: DatabaseSession) -> dict:
    try:
        return _testing_workflow(session).traceability(requirement_version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Requirement version not found") from exc


@router.get("/ai-value/experiments")
def list_ai_value_experiments(_principal: Reader, session: DatabaseSession) -> list[dict[str, object]]:
    runs = session.scalars(select(database_models.EvaluationRun).order_by(database_models.EvaluationRun.created_at.desc())).all()
    return [{
        "experiment_id": run.evaluation_run_id, "experiment": run.experiment_group,
        "variant": run.variant, "provider": run.provider, "model": run.model,
        "dataset_version": run.dataset_version, "status": run.status,
        "summary": run.summary,
    } for run in runs]


@router.post("/external-sync/{link_id}/retry")
def retry_external_sync(link_id: int, principal: SyncOperator, session: DatabaseSession) -> dict[str, object]:
    try:
        link = _testing_workflow(session).retry_external_sync(
            link_id,
            actor_principal_id=principal.principal_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="External sync record not found") from exc
    except WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"link_id": link.link_id, "issue_key": link.issue_key, "sync_status": link.sync_status, "sync_error": link.sync_error, "retry_count": link.retry_count}
