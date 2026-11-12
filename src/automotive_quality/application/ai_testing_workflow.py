from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from automotive_quality.domains.ai.schemas import RCAEvidenceItem, RCAEvidenceRequest
from automotive_quality.domains.ai.workflows import AIWorkflowService
from automotive_quality.infrastructure.database import models
from automotive_quality.integrations.issue_tracker import IssueTracker
from automotive_quality.integrations.outbound_security import safe_external_error
from automotive_quality.shared.security_logging import log_security_event


class WorkflowConflict(ValueError):
    pass


class ExternalSyncUnavailable(RuntimeError):
    pass


class AITestingWorkflow:
    def __init__(self, session: Session, ai: AIWorkflowService, tracker: IssueTracker, approved_statuses: set[str], rejected_statuses: set[str]) -> None:
        self.session = session
        self.ai = ai
        self.tracker = tracker
        self.approved_statuses = {value.casefold() for value in approved_statuses}
        self.rejected_statuses = {value.casefold() for value in rejected_statuses}

    def import_requirement(
        self,
        issue_key: str,
        actor_principal_id: str | None = None,
    ) -> models.RequirementVersion:
        try:
            issue = self.tracker.get_issue(issue_key)
        except Exception as exc:
            log_security_event("external_sync_failure", reason=safe_external_error(exc).split(":", 1)[0])
            raise ExternalSyncUnavailable("External requirement service is unavailable") from exc
        if (
            not issue.get("summary")
            or len(issue["summary"]) > 512
            or len(issue.get("description", "")) > 12_000
        ):
            raise WorkflowConflict("External requirement content violates input limits")
        content = f"{issue['summary']}\n{issue['description']}"
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        latest = self.session.scalar(select(models.RequirementVersion).where(models.RequirementVersion.external_reference == issue_key).order_by(models.RequirementVersion.version.desc()))
        if latest and latest.content_hash == content_hash:
            return latest
        version = (latest.version + 1) if latest else 1
        record = models.RequirementVersion(
            requirement_version_id=f"REQV-{uuid4().hex[:12].upper()}", requirement_id=f"REQ-{issue_key}", version=version,
            external_system=self.tracker.name, external_reference=issue_key, summary=issue["summary"],
            description=issue["description"], acceptance_criteria=issue["description"], content_hash=content_hash,
            created_by_principal_id=actor_principal_id,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def analyze(self, requirement_version_id: str) -> dict:
        requirement = self._requirement(requirement_version_id)
        result = self.ai.analyze_requirement(f"{requirement.summary}\n{requirement.description}")
        try:
            requirement.analysis = result.model_dump(mode="json")
            requirement.analysis_ai_run_id = self.ai.last_run_id
            self.session.flush()
        except Exception as exc:
            self.session.rollback()
            self.ai.mark_business_failure("requirement_analysis_persistence", exc)
            raise
        return {"requirement_version_id": requirement_version_id, "ai_run_id": self.ai.last_run_id, "analysis": requirement.analysis}

    def generate_tests(
        self,
        requirement_version_id: str,
        actor_principal_id: str | None = None,
    ) -> dict:
        requirement = self._requirement(requirement_version_id)
        if requirement.analysis is None:
            self.analyze(requirement_version_id)
        from automotive_quality.domains.ai.schemas import RequirementAnalysis

        suite = self.ai.generate_tests(requirement.description, RequirementAnalysis.model_validate(requirement.analysis))
        ai_run_id = self.ai.last_run_id
        seen: set[str] = set()
        case_ids: list[str] = []
        version_ids: list[str] = []
        provider_test_ids: list[str] = []
        rejected = 0
        try:
            for case in suite.cases:
                signature = case.title.strip().casefold()
                if signature in seen or not case.steps or not case.expected_result.strip():
                    rejected += 1
                    continue
                seen.add(signature)

                # Provider test IDs are untrusted display metadata. Each generated
                # occurrence is a new artifact; the platform owns persistent IDs.
                case_id = f"TC-{uuid4().hex.upper()}"
                version_id = f"TCV-{uuid4().hex.upper()}"
                content = case.model_dump(mode="json")
                content["provider_test_id"] = case.test_id
                content["platform_test_case_id"] = case_id
                parent = models.TestCase(
                    test_case_id=case_id,
                    suite=f"REQ-{requirement.external_reference}",
                    title=case.title,
                    severity=case.priority,
                    specification=content,
                    review_status="REVIEW_REQUIRED",
                )
                self.session.add(parent)
                self.session.add(models.TestCaseVersion(
                    test_case_version_id=version_id,
                    test_case_id=case_id,
                    version=1,
                    requirement_version_id=requirement_version_id,
                    source_ai_run_id=ai_run_id,
                    generated_by_principal_id=actor_principal_id,
                    status="REVIEW_REQUIRED",
                    content=content,
                ))
                case_ids.append(case_id)
                version_ids.append(version_id)
                provider_test_ids.append(case.test_id)
            if not version_ids:
                raise WorkflowConflict("AI output contained no reviewable test cases")
            review_id = f"REV-{uuid4().hex[:12].upper()}"
            review = models.ReviewRequest(review_id=review_id, artifact_type="TEST_CASE_BATCH", artifact_ids=version_ids, status="REVIEW_REQUIRED", external_system=self.tracker.name)
            self.session.add(review)
            self.session.flush()
            link = models.ExternalIssueLink(provider=self.tracker.name, issue_key=None, issue_url=None, artifact_type="REVIEW", artifact_id=review_id, idempotency_key=f"review:{review_id}", sync_status="PENDING", retry_count=0)
            self.session.add(link)
            self.session.commit()  # Drafts and review survive an external tracker outage.
        except Exception as exc:
            self.session.rollback()
            self.ai.mark_business_failure("generated_test_persistence", exc)
            raise
        self._sync_link(link)
        return {"generation_run_id": ai_run_id, "generated": len(suite.cases), "accepted_for_review": len(version_ids), "rejected_by_validation": rejected, "review_id": review_id, "issue_key": link.issue_key, "sync_status": link.sync_status, "test_case_ids": case_ids, "test_case_version_ids": version_ids, "provider_test_ids": provider_test_ids}

    def sync_review(self, review_id: str) -> models.ReviewRequest:
        review = self.session.get(models.ReviewRequest, review_id)
        if review is None:
            raise KeyError(review_id)
        link = self.session.scalar(select(models.ExternalIssueLink).where(models.ExternalIssueLink.artifact_type == "REVIEW", models.ExternalIssueLink.artifact_id == review_id))
        if link is None or not link.issue_key:
            raise WorkflowConflict("Review has no external issue")
        try:
            external_status = self.tracker.get_issue_status(link.issue_key)
        except Exception as exc:
            link.sync_status = "FAILED"
            link.sync_error = safe_external_error(exc)
            link.retry_count += 1
            self.session.commit()
            log_security_event("external_sync_failure", reason=link.sync_error.split(":", 1)[0])
            raise ExternalSyncUnavailable("External review synchronization is unavailable") from exc
        mapped = "APPROVED" if external_status.casefold() in self.approved_statuses else "REJECTED" if external_status.casefold() in self.rejected_statuses else "REVIEW_REQUIRED"
        if mapped != "REVIEW_REQUIRED":
            now = datetime.now(timezone.utc)
            for version_id in review.artifact_ids:
                version = self.session.get(models.TestCaseVersion, version_id)
                if version:
                    version.status = mapped
                    version.approved_at = now if mapped == "APPROVED" else None
                    parent = self.session.get(models.TestCase, version.test_case_id)
                    if parent:
                        parent.review_status = mapped
            review.completed_at = now
        review.status = mapped
        self.session.flush()
        return review

    def execute(
        self,
        requirement_version_id: str,
        test_case_version_ids: list[str],
        actuals: dict[str, str],
        dataset_version: str,
        actor_principal_id: str | None = None,
    ) -> dict:
        if not test_case_version_ids:
            raise WorkflowConflict("At least one test-case version is required")
        requested_ids = set(test_case_version_ids)
        if len(requested_ids) != len(test_case_version_ids):
            raise WorkflowConflict("Duplicate test-case version IDs are not allowed")
        if not actuals:
            raise WorkflowConflict("Actual results are required for every requested test-case version")
        if set(actuals) != requested_ids:
            raise WorkflowConflict("Actual-result keys must exactly match requested test-case version IDs")
        if any(not isinstance(actual, str) or not actual.strip() for actual in actuals.values()):
            raise WorkflowConflict("Actual results must be non-empty strings")

        datasets = self.session.scalars(
            select(models.DatasetVersion).where(
                (models.DatasetVersion.dataset_version_id == dataset_version)
                | (models.DatasetVersion.version == dataset_version)
            )
        ).all()
        if len(datasets) != 1:
            raise WorkflowConflict("Unknown or ambiguous dataset version")
        verified_dataset = datasets[0]

        versions = [self.session.get(models.TestCaseVersion, version_id) for version_id in test_case_version_ids]
        if any(version is None or version.requirement_version_id != requirement_version_id for version in versions):
            raise WorkflowConflict("Unknown test-case version for requirement")
        if any(version.status != "APPROVED" for version in versions if version):
            raise WorkflowConflict("Only APPROVED test-case versions are executable")
        run_id = f"TR-{uuid4().hex[:12].upper()}"
        now = datetime.now(timezone.utc)
        run = models.TestRun(
            test_run_id=run_id,
            suite=f"REQ-{requirement_version_id}",
            environment=dataset_version,
            status="RUNNING",
            started_at=now,
            submitted_by_principal_id=actor_principal_id,
        )
        failures: list[tuple[models.TestCaseVersion, models.TestResult, str]] = []
        try:
            self.session.add(run)
            # Persist the parent before adding results. TestRun and TestResult do
            # not expose an ORM relationship, so SQLAlchemy cannot infer ordering.
            self.session.flush()
            for version in versions:
                assert version is not None
                expected = str(version.content["expected_result"])
                actual = actuals[version.test_case_version_id]
                status = "PASSED" if actual == expected else "FAILED"
                result = models.TestResult(
                    test_run_id=run_id,
                    test_case_id=version.test_case_id,
                    test_case_version_id=version.test_case_version_id,
                    status=status,
                    expected=expected,
                    actual=actual,
                    affected_rows=0,
                    execution_ms=0,
                    evidence={
                        "dataset_version": verified_dataset.version,
                        "dataset_version_id": verified_dataset.dataset_version_id,
                        "execution_mode": "SUBMITTED_RESULTS_VALIDATION",
                        "result_source": "CALLER_SUBMITTED",
                        "submitted_by_principal_id": actor_principal_id,
                    },
                )
                self.session.add(result)
                if status == "FAILED":
                    signature = hashlib.sha256(
                        f"{version.test_case_version_id}|{actual}|{verified_dataset.dataset_version_id}".encode()
                    ).hexdigest()
                    failures.append((version, result, signature))
            self.session.flush()
            for _version, result, signature in failures:
                link = self.session.scalar(
                    select(models.ExternalIssueLink).where(models.ExternalIssueLink.idempotency_key == signature)
                )
                if link is None:
                    link = models.ExternalIssueLink(
                        provider=self.tracker.name,
                        issue_key=None,
                        issue_url=None,
                        artifact_type="TEST_RESULT",
                        artifact_id=str(result.result_id),
                        idempotency_key=signature,
                        sync_status="PENDING",
                        retry_count=0,
                    )
                    self.session.add(link)
                    self.session.flush()
                result.external_issue_link_id = link.link_id
            run.status = "FAILED" if failures else "PASSED"
            run.completed_at = datetime.now(timezone.utc)
            self.session.commit()  # Submitted evidence is durable before Jira or AI enrichment.
        except Exception:
            self.session.rollback()
            raise

        for _version, result, _signature in failures:
            link = self.session.get(models.ExternalIssueLink, result.external_issue_link_id)
            assert link is not None
            case_id = f"TEST-RESULT-{result.result_id}"
            evidence = RCAEvidenceRequest(
                case_id=case_id,
                evidence_items=[
                    RCAEvidenceItem(id="EV-TEST-RUN", content=run_id, case_id=case_id),
                    RCAEvidenceItem(
                        id="EV-TEST-CASE-VERSION",
                        content=str(result.test_case_version_id),
                        case_id=case_id,
                    ),
                    RCAEvidenceItem(id="EV-DATASET-VERSION", content=dataset_version, case_id=case_id),
                    RCAEvidenceItem(id="EV-EXPECTED", content=result.expected, case_id=case_id),
                    RCAEvidenceItem(id="EV-ACTUAL", content=result.actual, case_id=case_id),
                ],
            )
            try:
                rca = self.ai.analyze_rca(evidence)
                result.rca_ai_run_id = self.ai.last_run_id
                self.session.commit()
                self._sync_link(link, rca_comment="AI-assisted RCA\n" + json.dumps(rca.model_dump(mode="json"), indent=2))
            except Exception as exc:  # noqa: BLE001 - enrichment must never roll back deterministic results
                self.session.rollback()
                link = self.session.get(models.ExternalIssueLink, result.external_issue_link_id)
                assert link is not None
                link.sync_status = "FAILED"
                link.sync_error = safe_external_error(exc)
                link.retry_count += 1
                log_security_event("external_sync_failure", reason=link.sync_error.split(":", 1)[0])
                self.session.commit()
        failed = len(failures)
        total = len(versions)
        return {
            "test_run_id": run_id,
            "status": run.status,
            "execution_mode": "SUBMITTED_RESULTS_VALIDATION",
            "automatically_executed": False,
            "submitted_results": total,
            "passed": total - failed,
            "failed": failed,
            "total": total,
            "external_sync": [
                self.session.get(models.ExternalIssueLink, result.external_issue_link_id).sync_status
                for _, result, _ in failures
            ],
        }

    def traceability(self, requirement_version_id: str) -> dict:
        requirement = self._requirement(requirement_version_id)
        versions = self.session.scalars(select(models.TestCaseVersion).where(models.TestCaseVersion.requirement_version_id == requirement_version_id)).all()
        version_ids = {version.test_case_version_id for version in versions}
        reviews = self.session.scalars(select(models.ReviewRequest)).all()
        linked_reviews = [review for review in reviews if version_ids.intersection(review.artifact_ids)]
        results = self.session.scalars(select(models.TestResult).where(models.TestResult.test_case_version_id.in_(version_ids))).all() if version_ids else []
        run_ids = {result.test_run_id for result in results}
        runs = self.session.scalars(select(models.TestRun).where(models.TestRun.test_run_id.in_(run_ids))).all() if run_ids else []
        link_ids = {result.external_issue_link_id for result in results if result.external_issue_link_id}
        review_ids = {review.review_id for review in linked_reviews}
        links = self.session.scalars(select(models.ExternalIssueLink).where((models.ExternalIssueLink.link_id.in_(link_ids)) | ((models.ExternalIssueLink.artifact_type == "REVIEW") & (models.ExternalIssueLink.artifact_id.in_(review_ids))))).all() if link_ids or review_ids else []
        rca_ids = {result.rca_ai_run_id for result in results if result.rca_ai_run_id}
        rca_runs = self.session.scalars(select(models.AIRun).where(models.AIRun.run_id.in_(rca_ids))).all() if rca_ids else []
        return {"requirement": {"id": requirement_version_id, "external_reference": requirement.external_reference, "version": requirement.version, "analysis_ai_run_id": requirement.analysis_ai_run_id}, "test_case_versions": [{"id": item.test_case_version_id, "test_case_id": item.test_case_id, "provider_test_id": item.content.get("provider_test_id", item.content.get("test_id")), "status": item.status, "source_ai_run_id": item.source_ai_run_id} for item in versions], "reviews": [{"id": item.review_id, "status": item.status} for item in linked_reviews], "test_runs": [{"id": item.test_run_id, "status": item.status, "dataset_version": item.environment} for item in runs], "test_results": [{"id": item.result_id, "test_run_id": item.test_run_id, "test_case_id": item.test_case_id, "test_case_version_id": item.test_case_version_id, "status": item.status, "rca_ai_run_id": item.rca_ai_run_id, "external_issue_link_id": item.external_issue_link_id} for item in results], "rca_ai_runs": [{"id": item.run_id, "prompt_version": item.prompt_version, "model": item.model, "provider": item.provider} for item in rca_runs], "external_issues": [{"link_id": item.link_id, "issue_key": item.issue_key, "artifact_type": item.artifact_type, "artifact_id": item.artifact_id, "sync_status": item.sync_status} for item in links]}

    def retry_external_sync(
        self,
        link_id: int,
        actor_principal_id: str | None = None,
    ) -> models.ExternalIssueLink:
        link = self.session.get(models.ExternalIssueLink, link_id)
        if link is None:
            raise KeyError(link_id)
        if link.artifact_type == "REVIEW":
            if self.session.get(models.ReviewRequest, link.artifact_id) is None:
                raise WorkflowConflict("External sync review relationship is invalid")
        elif link.artifact_type == "TEST_RESULT":
            try:
                result_id = int(link.artifact_id)
            except (TypeError, ValueError):
                raise WorkflowConflict("External sync test-result relationship is invalid") from None
            if self.session.get(models.TestResult, result_id) is None:
                raise WorkflowConflict("External sync test-result relationship is invalid")
        else:
            raise WorkflowConflict("Unsupported external sync artifact type")
        link.last_retry_by_principal_id = actor_principal_id
        comment = None
        if link.artifact_type == "TEST_RESULT":
            result = self.session.get(models.TestResult, int(link.artifact_id))
            if result and result.rca_ai_run_id:
                ai_run = self.session.get(models.AIRun, result.rca_ai_run_id)
                if ai_run:
                    comment = "AI-assisted RCA\n" + json.dumps(ai_run.output, indent=2)
        self._sync_link(link, rca_comment=comment)
        return link

    def _sync_link(self, link: models.ExternalIssueLink, rca_comment: str | None = None) -> None:
        try:
            if link.artifact_type == "REVIEW":
                review = self.session.get(models.ReviewRequest, link.artifact_id)
                assert review is not None
                issue_key = self.tracker.create_review_issue(summary=f"Review AI-generated test batch {review.review_id}", description=f"Review: {review.review_id}\nTests: {', '.join(review.artifact_ids)}", external_id=link.idempotency_key)
            else:
                result = self.session.get(models.TestResult, int(link.artifact_id))
                assert result is not None
                issue_key = self.tracker.create_defect(summary=f"[Automated Test Failure] {result.test_case_id}", description=f"Test run: {result.test_run_id}\nExpected: {result.expected}\nActual: {result.actual}", external_id=link.idempotency_key)
            link.issue_key = issue_key
            link.issue_url = self.tracker.issue_url(issue_key)
            if rca_comment:
                self.tracker.add_comment(issue_key, rca_comment)
            link.sync_status = "SUCCEEDED"
            link.sync_error = None
            link.synced_at = datetime.now(timezone.utc)
        except Exception as exc:  # noqa: BLE001 - external failure is durable retry state
            link.sync_status = "FAILED"
            link.sync_error = safe_external_error(exc)
            link.retry_count += 1
            log_security_event("external_sync_failure", reason=link.sync_error.split(":", 1)[0])
        self.session.commit()

    def _requirement(self, requirement_version_id: str) -> models.RequirementVersion:
        record = self.session.get(models.RequirementVersion, requirement_version_id)
        if record is None:
            raise KeyError(requirement_version_id)
        return record
