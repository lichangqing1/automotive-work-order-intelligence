from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .dataset_versions import UnknownDatasetVersion, resolve_dataset_version
from .models import WorkOrderSnapshot


class PostgresCaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve_version_id(self, version: str) -> str | None:
        try:
            return resolve_dataset_version(self.session, version).dataset_version_id
        except UnknownDatasetVersion:
            return None

    def list_cases(self, dataset_version: str) -> list[dict[str, object]]:
        version_id = self.resolve_version_id(dataset_version)
        if version_id is None:
            return []
        snapshots = self.session.scalars(
            select(WorkOrderSnapshot).where(WorkOrderSnapshot.dataset_version_id == version_id)
        ).all()
        return [snapshot.payload for snapshot in snapshots if snapshot.payload.get("resolution")]
