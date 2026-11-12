from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DatasetVersion


class UnknownDatasetVersion(KeyError):
    pass


class AmbiguousDatasetVersion(ValueError):
    pass


def resolve_dataset_version(session: Session, reference: str) -> DatasetVersion:
    """Resolve a canonical ID or a unique human version label without fallback."""
    record = session.get(DatasetVersion, reference)
    if record is not None:
        return record
    records = session.scalars(select(DatasetVersion).where(DatasetVersion.version == reference)).all()
    if not records:
        raise UnknownDatasetVersion(reference)
    if len(records) != 1:
        raise AmbiguousDatasetVersion(reference)
    return records[0]
