from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Dataset(Base):
    __tablename__ = "datasets"
    dataset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    source_type: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    dataset_version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.dataset_id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(32))
    row_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("dataset_id", "version"),)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    ingestion_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.dataset_version_id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    ingested_rows: Mapped[int] = mapped_column(Integer, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Vehicle(Base):
    __tablename__ = "vehicles"
    vehicle_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    vehicle_model: Mapped[str] = mapped_column(String(64), index=True)
    production_year: Mapped[int] = mapped_column(Integer)
    hardware_version: Mapped[str] = mapped_column(String(32))
    software_version: Mapped[str] = mapped_column(String(32))
    ota_version: Mapped[str | None] = mapped_column(ForeignKey("ota_releases.ota_version"))
    region: Mapped[str] = mapped_column(String(32))


class OTARelease(Base):
    __tablename__ = "ota_releases"
    ota_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    release_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    release_notes: Mapped[str] = mapped_column(Text)
    known_issue: Mapped[str | None] = mapped_column(Text)


class ServiceCenter(Base):
    __tablename__ = "service_centers"
    service_center_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    region: Mapped[str] = mapped_column(String(32))


class WorkOrder(Base):
    __tablename__ = "work_orders"
    work_order_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(ForeignKey("vehicles.vehicle_id"), index=True)
    service_center_id: Mapped[str | None] = mapped_column(ForeignKey("service_centers.service_center_id"))
    service_type: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(64), index=True)
    priority: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    ota_version: Mapped[str | None] = mapped_column(ForeignKey("ota_releases.ota_version"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    sla_hours: Mapped[int] = mapped_column(Integer)
    assigned_team: Mapped[str | None] = mapped_column(String(64), index=True)
    resolution_hours: Mapped[float | None] = mapped_column(Float)
    sla_breach: Mapped[bool | None]


class WorkOrderSnapshot(Base):
    __tablename__ = "work_order_snapshots"
    snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.dataset_version_id", ondelete="CASCADE"), index=True)
    work_order_id: Mapped[str] = mapped_column(String(32), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    row_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("dataset_version_id", "work_order_id"),)


class DiagnosticEvent(Base):
    __tablename__ = "diagnostic_events"
    event_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.work_order_id", ondelete="CASCADE"), index=True)
    error_code: Mapped[str] = mapped_column(String(64))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ResolutionHistory(Base):
    __tablename__ = "resolution_history"
    resolution_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.work_order_id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    resolution: Mapped[str] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("work_order_id", "version"),)


class DQRule(Base):
    __tablename__ = "dq_rules"
    rule_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT")
    active_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DQRuleVersion(Base):
    __tablename__ = "dq_rule_versions"
    version_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("dq_rules.rule_id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    rule_type: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(24))
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("rule_id", "version"),)


class RunMixin:
    status: Mapped[str] = mapped_column(String(24), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DQRun(RunMixin, Base):
    __tablename__ = "dq_runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(64))


class DQResult(Base):
    __tablename__ = "dq_results"
    result_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("dq_runs.run_id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("dq_rules.rule_id"))
    rule_version_id: Mapped[int] = mapped_column(ForeignKey("dq_rule_versions.version_id"), index=True)
    status: Mapped[str] = mapped_column(String(24))
    failed_count: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class TestCase(Base):
    __tablename__ = "test_cases"
    test_case_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    suite: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(256))
    version: Mapped[int] = mapped_column(Integer, default=1)
    severity: Mapped[str] = mapped_column(String(16))
    specification: Mapped[dict[str, Any]] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(24), default="APPROVED")


class TestRun(RunMixin, Base):
    __tablename__ = "test_runs"
    test_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    suite: Mapped[str] = mapped_column(String(128), index=True)
    environment: Mapped[str] = mapped_column(String(64))


class TestResult(Base):
    __tablename__ = "test_results"
    result_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.test_run_id", ondelete="CASCADE"), index=True)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.test_case_id"))
    test_case_version_id: Mapped[str | None] = mapped_column(ForeignKey("test_case_versions.test_case_version_id"), index=True)
    rca_ai_run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_runs.run_id"), index=True)
    external_issue_link_id: Mapped[int | None] = mapped_column(ForeignKey("external_issue_links.link_id"), index=True)
    status: Mapped[str] = mapped_column(String(24))
    expected: Mapped[str] = mapped_column(Text)
    actual: Mapped[str] = mapped_column(Text)
    affected_rows: Mapped[int] = mapped_column(Integer, default=0)
    execution_ms: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("test_run_id", "test_case_id"),)


class AIRun(Base):
    __tablename__ = "ai_runs"
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    output: Mapped[dict[str, Any]] = mapped_column(JSON)
    schema_valid: Mapped[bool]
    status: Mapped[str] = mapped_column(String(24), default="SUCCEEDED")
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RequirementVersion(Base):
    __tablename__ = "requirement_versions"
    requirement_version_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requirement_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    external_system: Mapped[str] = mapped_column(String(32))
    external_reference: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    analysis_ai_run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_runs.run_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("requirement_id", "version"),)


class TestCaseVersion(Base):
    __tablename__ = "test_case_versions"
    test_case_version_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.test_case_id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    requirement_version_id: Mapped[str] = mapped_column(ForeignKey("requirement_versions.requirement_version_id"), index=True)
    source_ai_run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_runs.run_id"))
    status: Mapped[str] = mapped_column(String(24), index=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("test_case_id", "version"),)


class ReviewRequest(Base):
    __tablename__ = "review_requests"
    review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_type: Mapped[str] = mapped_column(String(32))
    artifact_ids: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), index=True)
    external_system: Mapped[str | None] = mapped_column(String(32))
    reviewer: Mapped[str | None] = mapped_column(String(128))
    review_comment: Mapped[str | None] = mapped_column(Text)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_review_seconds: Mapped[float | None] = mapped_column(Float)
    was_modified: Mapped[bool | None]
    rejection_reasons: Mapped[list[str] | None] = mapped_column(JSON)
    validated_coverage: Mapped[dict[str, list[str]] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalIssueLink(Base):
    __tablename__ = "external_issue_links"
    link_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32))
    issue_key: Mapped[str | None] = mapped_column(String(64), index=True)
    issue_url: Mapped[str | None] = mapped_column(String(512))
    artifact_type: Mapped[str] = mapped_column(String(32))
    artifact_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    sync_status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    sync_error: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationRun(RunMixin, Base):
    __tablename__ = "evaluation_runs"
    evaluation_run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_name: Mapped[str] = mapped_column(String(128))
    dataset_version: Mapped[str] = mapped_column(String(32))
    experiment_group: Mapped[str | None] = mapped_column(String(64), index=True)
    variant: Mapped[str | None] = mapped_column(String(32), index=True)
    baseline_type: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    dataset_hash: Mapped[str | None] = mapped_column(String(64))
    run_number: Mapped[int | None] = mapped_column(Integer)
    configuration: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    raw_outputs: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class EvaluationMetric(Base):
    __tablename__ = "evaluation_metrics"
    metric_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.evaluation_run_id", ondelete="CASCADE"), index=True)
    metric_name: Mapped[str] = mapped_column(String(128))
    metric_value: Mapped[float] = mapped_column(Float)
    sample_id: Mapped[str | None] = mapped_column(String(64), index=True)
