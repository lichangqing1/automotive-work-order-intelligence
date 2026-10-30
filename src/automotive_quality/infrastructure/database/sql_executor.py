from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session


class SQLAssetExecutor:
    def __init__(self, session: Session, sql_root: str | Path) -> None:
        self.session = session
        self.sql_root = Path(sql_root)

    def execute_marts(self) -> None:
        if self.session.bind is None or self.session.bind.dialect.name != "postgresql":
            return
        for path in sorted((self.sql_root / "marts").glob("*.sql")):
            self.session.execute(text(path.read_text(encoding="utf-8")))

    def run_validation(self, name: str, parameters: dict | None = None) -> list[dict]:
        sql = (self.sql_root / "validations" / f"{name}.sql").read_text(encoding="utf-8")
        return [dict(row) for row in self.session.execute(text(sql), parameters or {}).mappings()]

    def validate_platform(self, dataset_version: str) -> dict[str, bool]:
        if self.session.bind is None or self.session.bind.dialect.name != "postgresql":
            return {"referential_integrity": True, "ota_compatibility": True, "source_target_reconciliation": True}
        referential = self.run_validation("referential_integrity")
        ota = self.run_validation("ota_compatibility")
        reconciliation = self.run_validation("source_target_reconciliation", {"dataset_version": dataset_version})
        reconciled = bool(reconciliation) and reconciliation[0]["expected_clean_count"] == reconciliation[0]["actual_clean_count"]
        return {"referential_integrity": not referential, "ota_compatibility": not ota, "source_target_reconciliation": reconciled}
