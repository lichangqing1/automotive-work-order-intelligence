from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from automotive_quality.domains.ai.workflows import AIWorkflowService
from automotive_quality.infrastructure.database import models
from automotive_quality.integrations.issue_tracker import IssueTracker


class WorkflowConflict(ValueError):
    pass


class AITestingWorkflow:
    def __init__(self, session: Session, ai: AIWorkflowService, tracker: IssueTracker, approved_statuses: set[str], rejected_statuses: set[str]) -> None:
        self.session = session
        self.ai = ai
        self.tracker = tracker
        self.approved_statuses = {value.casefold() for value in approved_statuses}
        self.rejected_statuses = {value.casefold() for value in rejected_statuses}

    def import_requirement(self, issue_key: str) -> models.RequirementVersion:
        issue = self.tracker.get_issue(issue_key)
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
        )
        self.session.add(record)
        self.session.flush()
        return record

    def analyze(self, requirement_version_id: str) -> dict:
        requirement = self._requirement(requirement_version_id)
        result = self.ai.analyze_requirement(f"{requirement.summary}\n{requirement.description}")
        requirement.analysis = result.model_dump(mode="json")
        requirement.analysis_ai_run_id = self.ai.last_run_id
        self.session.flush()
        return {"requirement_version_id": requirement_version_id, "ai_run_id": self.ai.last_run_id, "analysis": requirement.analysis}

    def generate_tests(self, requirement_version_id: str) -> dict:
        requirement = self._requirement(requirement_version_id)
        if requirement.analysis is None:
            self.analyze(requirement_version_id)
        from automotive_quality.domains.ai.schemas import RequirementAnalysis

        suite = self.ai.generate_tests(requirement.description, RequirementAnalysis.model_validate(requirement.analysis))
        ai_run_id = self.ai.last_run_id
        seen: set[str] = set()
        version_ids: list[str] = []
        rejected = 0
        for case in suite.cases:
            signature = case.title.strip().casefold()
            if signature in seen or not case.steps or not case.expected_result.strip():
                rejected += 1
                continue
            seen.add(signature)
            case_id = case.test_id
            parent = self.session.get(models.TestCase, case_id)
            if parent is None:
                parent = models.TestCase(test_case_id=case_id, suite=f"REQ-{requirement.external_reference}", title=case.title, severity=case.priority, specification=case.model_dump(mode="json"), review_status="REVIEW_REQUIRED")
                self.session.add(parent)
            version_number = int(self.session.scalar(select(func.max(models.TestCaseVersion.version)).where(models.TestCaseVersion.test_case_id == case_id)) or 0) + 1
            version_id = f"TCV-{uuid4().hex[:12].upper()}"
            self.session.add(models.TestCaseVersion(test_case_version_id=version_id, test_case_id=case_id, version=version_number, requirement_version_id=requirement_version_id, source_ai_run_id=ai_run_id, status="REVIEW_REQUIRED", content=case.model_dump(mode="json")))
            version_ids.append(version_id)
        if not version_ids:
            raise WorkflowConflict("AI output contained no reviewable test cases")
        review_id = f"REV-{uuid4().hex[:12].upper()}"
        review = models.ReviewRequest(review_id=review_id, artifact_type="TEST_CASE_BATCH", artifact_ids=version_ids, status="REVIEW_REQUIRED", external_system=self.tracker.name)
        self.session.add(review)
        self.session.flush()
        link = models.ExternalIssueLink(provider=self.tracker.name, issue_key=None, issue_url=None, artifact_type="REVIEW", artifact_id=review_id, idempotency_key=f"review:{review_id}", sync_status="PENDING", retry_count=0)
        self.session.add(link)
        self.session.commit()  # Drafts and review survive an external tracker outage.
        self._sync_link(link)
        return {"generation_run_id": ai_run_id, "generated": len(suite.cases), "accepted_for_review": len(version_ids), "rejected_by_validation": rejected, "review_id": review_id, "issue_key": link.issue_key, "sync_status": link.sync_status, "test_case_version_ids": version_ids}

    def sync_review(self, review_id: str) -> models.ReviewRequest:
        review = self.session.get(models.ReviewRequest, review_id)
        if review is None:
            raise KeyError(review_id)
        link = self.session.scalar(select(models.ExternalIssueLink).where(models.ExternalIssueLink.artifact_type == "REVIEW", models.ExternalIssueLink.artifact_id == review_id))
        if link is None or not link.issue_key:
            raise WorkflowConflict("Review has no external issue")
        external_status = self.tracker.get_issue_status(link.issue_key)
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

    def execute(self, requirement_version_id: str, test_case_version_ids: list[str], actuals: dict[str, str], dataset_version: str) -> dict:
        versions = [self.session.get(models.TestCaseVersion, version_id) for version_id in test_case_version_ids]
        if any(version is None or version.requirement_version_id != requirement_version_id for version in versions):
            raise WorkflowConflict("Unknown test-case version for requirement")
        if any(version.status != "APPROVED" for version in versions if version):
            raise WorkflowConflict("Only APPROVED test-case versions are executable")
        run_id = f"TR-{uuid4().hex[:12].upper()}"
        now = datetime.now(timezone.utc)
        run = models.TestRun(test_run_id=run_id, suite=f"REQ-{requirement_version_id}", environment=dataset_version, status="RUNNING", started_at=now)
        self.session.add(run)
        # Persist the parent before adding results. TestRun and TestResult do not
        # expose an ORM relationship, so SQLAlchemy cannot derive their insert
        # ordering solely from assigning the foreign-key string.
        self.session.flush()
        failures: list[tuple[models.TestCaseVersion, models.TestResult, str]] = []
        for version in versions:
            assert version is not None
            expected = str(version.content["expected_result"])
            actual = actuals.get(version.test_case_version_id, expected)
            status = "PASSED" if actual == expected else "FAILED"
            result = models.TestResult(test_run_id=run_id, test_case_id=version.test_case_id, test_case_version_id=version.test_case_version_id, status=status, expected=expected, actual=actual, affected_rows=0, execution_ms=0, evidence={"dataset_version": dataset_version})
            self.session.add(result)
            if status == "FAILED":
                signature = hashlib.sha256(f"{version.test_case_version_id}|{actual}|{dataset_version}".encode()).hexdigest()
                failures.append((version, result, signature))
        self.session.flush()
        for _version, result, signature in failures:
            link = self.session.scalar(select(models.ExternalIssueLink).where(models.ExternalIssueLink.idempotency_key == signature))
            if link is None:
                link = models.ExternalIssueLink(provider=self.tracker.name, issue_key=None, issue_url=None, artifact_type="TEST_RESULT", artifact_id=str(result.result_id), idempotency_key=signature, sync_status="PENDING", retry_count=0)
                self.session.add(link)
                self.session.flush()
            result.external_issue_link_id = link.link_id
        run.status = "FAILED" if failures else "PASSED"
        run.completed_at = datetime.now(timezone.utc)
        self.session.commit()  # Deterministic run/results are durable before Jira or AI enrichment.
        for _version, result, _signature in failures:
            link = self.session.get(models.ExternalIssueLink, result.external_issue_link_id)
            assert link is not None
            evidence = {"test_result_id": result.result_id, "test_run": run_id, "test_case_version": result.test_case_version_id, "dataset_version": dataset_version, "expected": result.expected, "actual": result.actual}
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
                link.sync_error = f"{type(exc).__name__}: {exc}"
                link.retry_count += 1
                self.session.commit()
        return {"test_run_id": run_id, "status": run.status, "failed": len(failures), "total": len(versions), "external_sync": [self.session.get(models.ExternalIssueLink, result.external_issue_link_id).sync_status for _, result, _ in failures]}

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
        return {"requirement": {"id": requirement_version_id, "external_reference": requirement.external_reference, "version": requirement.version, "analysis_ai_run_id": requirement.analysis_ai_run_id}, "test_case_versions": [{"id": item.test_case_version_id, "test_case_id": item.test_case_id, "status": item.status, "source_ai_run_id": item.source_ai_run_id} for item in versions], "reviews": [{"id": item.review_id, "status": item.status} for item in linked_reviews], "test_runs": [{"id": item.test_run_id, "status": item.status, "dataset_version": item.environment} for item in runs], "test_results": [{"id": item.result_id, "test_run_id": item.test_run_id, "test_case_version_id": item.test_case_version_id, "status": item.status, "rca_ai_run_id": item.rca_ai_run_id, "external_issue_link_id": item.external_issue_link_id} for item in results], "rca_ai_runs": [{"id": item.run_id, "prompt_version": item.prompt_version, "model": item.model, "provider": item.provider} for item in rca_runs], "external_issues": [{"link_id": item.link_id, "issue_key": item.issue_key, "artifact_type": item.artifact_type, "artifact_id": item.artifact_id, "sync_status": item.sync_status} for item in links]}

    def retry_external_sync(self, link_id: int) -> models.ExternalIssueLink:
        link = self.session.get(models.ExternalIssueLink, link_id)
        if link is None:
            raise KeyError(link_id)
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
            link.sync_error = f"{type(exc).__name__}: {exc}"
            link.retry_count += 1
        self.session.commit()

    def _requirement(self, requirement_version_id: str) -> models.RequirementVersion:
        record = self.session.get(models.RequirementVersion, requirement_version_id)
        if record is None:
            raise KeyError(requirement_version_id)
        return record
