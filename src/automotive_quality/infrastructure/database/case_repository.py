from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DatasetVersion, WorkOrderSnapshot


class PostgresCaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def resolve_version_id(self, version: str) -> str | None:
        if version.startswith("DSV-") and self.session.get(DatasetVersion, version):
            return version
        return self.session.scalar(select(DatasetVersion.dataset_version_id).where(DatasetVersion.version == version))

    def list_cases(self, dataset_version: str) -> list[dict[str, object]]:
        version_id = self.resolve_version_id(dataset_version)
        if version_id is None:
            return []
        snapshots = self.session.scalars(
            select(WorkOrderSnapshot).where(WorkOrderSnapshot.dataset_version_id == version_id)
        ).all()
        return [snapshot.payload for snapshot in snapshots if snapshot.payload.get("resolution")]
