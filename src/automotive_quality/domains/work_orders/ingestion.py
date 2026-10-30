from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

import pandas as pd
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.sources.synthetic import WorkOrderDataset


class IngestionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIALLY_SUCCEEDED = "PARTIALLY_SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class IngestionSummary:
    run_id: str
    status: IngestionStatus
    ingested_rows: int
    rejected_rows: int


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [{key: (None if pd.isna(value) else value) for key, value in row.items()} for row in frame.to_dict("records")]


def _frame_hash(frame: pd.DataFrame) -> str:
    normalized = frame.sort_index(axis=1).reset_index(drop=True)
    return hashlib.sha256(pd.util.hash_pandas_object(normalized, index=True).values.tobytes()).hexdigest()


def ingest_generated_dataset(session: Session, data: WorkOrderDataset, *, version: str = "1", rejected_rows: int = 0) -> IngestionSummary:
    """Persist a generator source through an ingestion boundary; downstream logic is source-agnostic."""
    dataset_id = "DS-AUTOMOTIVE-WORK-ORDERS"
    version_id = f"DSV-{version}"
    run_id = f"ING-{uuid4().hex[:12].upper()}"
    now = datetime.now(timezone.utc)
    manifest = {
        "work_orders": _frame_hash(data.work_orders),
        "vehicles": _frame_hash(data.vehicles),
        "ota_releases": _frame_hash(data.ota_releases),
        "diagnostic_events": _frame_hash(data.diagnostic_events),
    }
    content_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    session.merge(models.Dataset(dataset_id=dataset_id, name="Automotive Work Orders", source_type="synthetic"))
    session.merge(models.DatasetVersion(dataset_version_id=version_id, dataset_id=dataset_id, version=version, row_count=len(data.work_orders), content_hash=content_hash))
    run = models.IngestionRun(ingestion_run_id=run_id, dataset_version_id=version_id, status=IngestionStatus.RUNNING, started_at=now, rejected_rows=rejected_rows)
    session.add(run)
    session.flush()
    try:
        for row in _records(data.ota_releases):
            session.merge(models.OTARelease(**row))
        center_ids = sorted(data.work_orders["service_center_id"].dropna().unique())
        for center_id in center_ids:
            session.merge(models.ServiceCenter(service_center_id=center_id, name=f"Service Center {center_id}", region="Unknown"))
        for row in _records(data.vehicles):
            session.merge(models.Vehicle(**row))
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
            row_hash = hashlib.sha256(json.dumps(snapshot_payload, sort_keys=True).encode()).hexdigest()
            session.add(models.WorkOrderSnapshot(dataset_version_id=version_id, work_order_id=str(row["work_order_id"]), payload=snapshot_payload, row_hash=row_hash))
            if row.get("resolution"):
                existing_history = session.query(models.ResolutionHistory).filter_by(work_order_id=row["work_order_id"], version=1).one_or_none()
                if existing_history is None:
                    session.add(models.ResolutionHistory(work_order_id=row["work_order_id"], version=1, resolution=str(row["resolution"])))
        for raw in _records(data.diagnostic_events):
            row = {
                "event_id": raw["event_id"], "work_order_id": raw["work_order_id"],
                "error_code": raw["error_code"], "event_time": raw["created_at"], "payload": {},
            }
            session.merge(models.DiagnosticEvent(**row))
        run.status = IngestionStatus.SUCCEEDED
        run.ingested_rows = len(data.work_orders)
        run.completed_at = datetime.now(timezone.utc)
        session.flush()
    except SQLAlchemyError as exc:
        run.status = IngestionStatus.FAILED
        run.error = str(exc)
        run.completed_at = datetime.now(timezone.utc)
        raise
    return IngestionSummary(run_id, IngestionStatus(run.status), run.ingested_rows, run.rejected_rows)
