from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.sources.synthetic import WorkOrderDataset


class IngestionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIALLY_SUCCEEDED = "PARTIALLY_SUCCEEDED"
    FAILED = "FAILED"


class IngestionDisposition(StrEnum):
    CREATED = "CREATED"
    ALREADY_INGESTED = "ALREADY_INGESTED"


class DatasetVersionConflict(ValueError):
    pass


class IncompleteDatasetVersion(RuntimeError):
    pass


@dataclass(frozen=True)
class IngestionSummary:
    run_id: str
    attempt_id: str
    dataset_version_id: str
    status: IngestionStatus
    disposition: IngestionDisposition
    ingested_rows: int
    rejected_rows: int


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [{key: (None if pd.isna(value) else value) for key, value in row.items()} for row in frame.to_dict("records")]


SOURCE_HASH_VERSION = "source-json-multiset-v1"


def _canonical_value(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _frame_hash(frame: pd.DataFrame) -> str:
    columns = sorted(str(column) for column in frame.columns)
    rows = [
        json.dumps(
            {column: _canonical_value(row[column]) for column in columns},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        for row in frame.to_dict("records")
    ]
    payload = json.dumps(sorted(rows), separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def dataset_content_hash(data: WorkOrderDataset) -> str:
    manifest = {
        "hash_version": SOURCE_HASH_VERSION,
        "work_orders": _frame_hash(data.work_orders),
        "vehicles": _frame_hash(data.vehicles),
        "ota_releases": _frame_hash(data.ota_releases),
        "diagnostic_events": _frame_hash(data.diagnostic_events),
    }
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def _audit_bind(session: Session):
    bind = session.get_bind()
    return getattr(bind, "engine", bind)


def _create_attempt(
    session: Session,
    *,
    attempt_id: str,
    dataset_id: str,
    version: str,
    version_id: str,
    content_hash: str,
    source_rows: int,
    rejected_rows: int,
) -> None:
    with Session(_audit_bind(session)) as audit:
        audit.add(models.IngestionAttempt(
            attempt_id=attempt_id,
            dataset_id=dataset_id,
            dataset_version_reference=version,
            dataset_version_id=version_id,
            source_content_hash=content_hash,
            source_hash_version=SOURCE_HASH_VERSION,
            status="RUNNING",
            source_rows=source_rows,
            rejected_rows=rejected_rows,
            started_at=datetime.now(timezone.utc),
        ))
        audit.commit()


def _complete_attempt(session: Session, attempt_id: str, **values: Any) -> None:
    with Session(_audit_bind(session)) as audit:
        attempt = audit.get(models.IngestionAttempt, attempt_id)
        if attempt is None:
            raise RuntimeError("Ingestion attempt audit record is missing")
        for key, value in values.items():
            setattr(attempt, key, value)
        attempt.completed_at = datetime.now(timezone.utc)
        audit.commit()


def _error_category(exc: Exception) -> str:
    if isinstance(exc, IntegrityError):
        return "DATABASE_CONSTRAINT"
    if isinstance(exc, SQLAlchemyError):
        return "DATABASE_ERROR"
    return "INTERNAL_ERROR"


def _existing_summary(
    session: Session,
    *,
    version_id: str,
    content_hash: str,
    clean_rows: int,
    rejected_rows: int,
    attempt_id: str,
) -> IngestionSummary | None:
    version = session.get(models.DatasetVersion, version_id)
    if version is None:
        return None
    runs = session.scalars(select(models.IngestionRun).where(
        models.IngestionRun.dataset_version_id == version_id
    )).all()
    snapshot_count = int(session.scalar(
        select(func.count()).select_from(models.WorkOrderSnapshot).where(
            models.WorkOrderSnapshot.dataset_version_id == version_id
        )
    ) or 0)
    if version.source_content_hash != content_hash:
        raise DatasetVersionConflict("Dataset version already exists with different immutable source content")
    if (
        len(runs) != 1
        or runs[0].status != IngestionStatus.SUCCEEDED
        or runs[0].ingested_rows != clean_rows
        or runs[0].rejected_rows != rejected_rows
        or snapshot_count != clean_rows
    ):
        raise IncompleteDatasetVersion("Dataset version exists without one complete, internally consistent ingestion")
    run = runs[0]
    return IngestionSummary(
        run.ingestion_run_id,
        attempt_id,
        version_id,
        IngestionStatus.SUCCEEDED,
        IngestionDisposition.ALREADY_INGESTED,
        run.ingested_rows,
        run.rejected_rows,
    )


def ingest_generated_dataset(
    session: Session,
    data: WorkOrderDataset,
    *,
    version: str = "1",
    rejected_rows: int = 0,
    source_content_hash: str | None = None,
    source_row_count: int | None = None,
) -> IngestionSummary:
    """Persist a generator source through an ingestion boundary; downstream logic is source-agnostic."""
    dataset_id = "DS-AUTOMOTIVE-WORK-ORDERS"
    version_id = f"DSV-{version}"
    run_id = f"ING-{uuid4().hex[:12].upper()}"
    attempt_id = f"IGA-{uuid4().hex[:16].upper()}"
    now = datetime.now(timezone.utc)
    content_hash = source_content_hash or dataset_content_hash(data)
    source_rows = source_row_count if source_row_count is not None else len(data.work_orders) + rejected_rows
    clean_rows = len(data.work_orders)
    _create_attempt(
        session,
        attempt_id=attempt_id,
        dataset_id=dataset_id,
        version=version,
        version_id=version_id,
        content_hash=content_hash,
        source_rows=source_rows,
        rejected_rows=rejected_rows,
    )
    stage = "identity_check"
    try:
        existing = _existing_summary(
            session,
            version_id=version_id,
            content_hash=content_hash,
            clean_rows=clean_rows,
            rejected_rows=rejected_rows,
            attempt_id=attempt_id,
        )
        if existing is not None:
            session.rollback()
            _complete_attempt(
                session,
                attempt_id,
                status="ALREADY_INGESTED",
                ingested_rows=existing.ingested_rows,
                ingestion_run_id=existing.run_id,
            )
            return existing

        stage = "dataset_identity"
        session.merge(models.Dataset(dataset_id=dataset_id, name="Automotive Work Orders", source_type="synthetic"))
        session.add(models.DatasetVersion(
            dataset_version_id=version_id,
            dataset_id=dataset_id,
            version=version,
            row_count=clean_rows,
            content_hash=content_hash,
            source_content_hash=content_hash,
            source_hash_version=SOURCE_HASH_VERSION,
        ))
        run = models.IngestionRun(
            ingestion_run_id=run_id,
            dataset_version_id=version_id,
            status=IngestionStatus.RUNNING,
            started_at=now,
            rejected_rows=rejected_rows,
        )
        session.add(run)
        session.flush()
        stage = "reference_data"
        for row in _records(data.ota_releases):
            session.merge(models.OTARelease(**row))
        center_ids = sorted(data.work_orders["service_center_id"].dropna().unique())
        for center_id in center_ids:
            session.merge(models.ServiceCenter(service_center_id=center_id, name=f"Service Center {center_id}", region="Unknown"))
        for row in _records(data.vehicles):
            session.merge(models.Vehicle(**row))
        stage = "work_order_snapshots"
        ota_by_vehicle = data.vehicles.set_index("vehicle_id")["ota_version"].to_dict()
        order_columns = {
            "work_order_id", "vehicle_id", "service_center_id", "service_type", "category", "priority", "status",
            "description", "error_code", "created_at", "resolved_at", "resolution", "sla_hours",
            "assigned_team", "resolution_hours", "sla_breach",
        }
        for raw in _records(data.work_orders):
            row = {key: value for key, value in raw.items() if key in order_columns}
            row["ota_version"] = ota_by_vehicle.get(row["vehicle_id"])
            session.merge(models.WorkOrder(**row))
            snapshot_payload = json.loads(json.dumps(raw, default=str))
            snapshot_payload["ota_version"] = row["ota_version"]
            row_hash = hashlib.sha256(json.dumps(snapshot_payload, sort_keys=True).encode()).hexdigest()
            session.add(models.WorkOrderSnapshot(dataset_version_id=version_id, work_order_id=str(row["work_order_id"]), payload=snapshot_payload, row_hash=row_hash))
            if row.get("resolution"):
                existing_history = session.query(models.ResolutionHistory).filter_by(work_order_id=row["work_order_id"], version=1).one_or_none()
                if existing_history is None:
                    session.add(models.ResolutionHistory(work_order_id=row["work_order_id"], version=1, resolution=str(row["resolution"])))
        for raw in _records(data.diagnostic_events):
            stage = "diagnostic_events"
            row = {
                "event_id": raw["event_id"], "work_order_id": raw["work_order_id"],
                "error_code": raw["error_code"], "event_time": raw["created_at"], "payload": {},
            }
            session.merge(models.DiagnosticEvent(**row))
        run.status = IngestionStatus.SUCCEEDED
        run.ingested_rows = len(data.work_orders)
        run.completed_at = datetime.now(timezone.utc)
        session.flush()
        session.commit()
    except (DatasetVersionConflict, IncompleteDatasetVersion) as exc:
        session.rollback()
        _complete_attempt(
            session,
            attempt_id,
            status="VERSION_CONFLICT",
            failure_stage=stage,
            error_category=type(exc).__name__.upper(),
            sanitized_error=str(exc),
        )
        raise
    except Exception as exc:
        session.rollback()
        try:
            with Session(_audit_bind(session)) as concurrent:
                existing = _existing_summary(
                    concurrent,
                    version_id=version_id,
                    content_hash=content_hash,
                    clean_rows=clean_rows,
                    rejected_rows=rejected_rows,
                    attempt_id=attempt_id,
                )
            if existing is not None:
                _complete_attempt(
                    session,
                    attempt_id,
                    status="ALREADY_INGESTED",
                    ingested_rows=existing.ingested_rows,
                    ingestion_run_id=existing.run_id,
                )
                return existing
        except DatasetVersionConflict as conflict:
            _complete_attempt(
                session,
                attempt_id,
                status="VERSION_CONFLICT",
                failure_stage="concurrent_identity_check",
                error_category="DATASETVERSIONCONFLICT",
                sanitized_error=str(conflict),
            )
            raise conflict from exc
        except IncompleteDatasetVersion:
            pass
        _complete_attempt(
            session,
            attempt_id,
            status="FAILED",
            failure_stage=stage,
            error_category=_error_category(exc),
            sanitized_error=f"Ingestion failed during {stage}",
        )
        raise
    _complete_attempt(
        session,
        attempt_id,
        status="SUCCEEDED",
        ingested_rows=clean_rows,
        ingestion_run_id=run_id,
    )
    return IngestionSummary(
        run_id,
        attempt_id,
        version_id,
        IngestionStatus.SUCCEEDED,
        IngestionDisposition.CREATED,
        clean_rows,
        rejected_rows,
    )
