from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from automotive_quality.domains.data_quality.io import load_rules
from automotive_quality.domains.data_quality.service import evaluate_rules
from automotive_quality.domains.work_orders.ingestion import IngestionSummary, ingest_generated_dataset
from automotive_quality.domains.work_orders.reconciliation import ReconciliationResult, reconcile_counts
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.repositories import DQRunRepository
from automotive_quality.infrastructure.database.sql_executor import SQLAssetExecutor
from automotive_quality.infrastructure.sources.synthetic import WorkOrderDataset


@dataclass(frozen=True)
class DefectDetectionMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    quarantined_rows: int


@dataclass(frozen=True)
class PlatformRunSummary:
    ingestion: IngestionSummary
    dq_run_id: str
    source_quality_passed: bool
    defect_detection_passed: bool
    publication_quality_passed: bool
    final_gate_passed: bool
    defect_metrics: DefectDetectionMetrics
    reconciliation: ReconciliationResult
    sql_validations: dict[str, bool]


class PlatformRuntime:
    def __init__(self, session: Session) -> None:
        self.session = session

    def execute(self, data: WorkOrderDataset, rules_path: str, *, dataset_version: str) -> PlatformRunSummary:
        rules = load_rules(rules_path)
        orders = data.work_orders.copy()
        orders["ota_version"] = orders["vehicle_id"].map(data.vehicles.set_index("vehicle_id")["ota_version"])
        source_quality = evaluate_rules(orders, rules, reference_tables={"vehicles": data.vehicles, "ota_releases": data.ota_releases})
        quarantined_indices = source_quality.failed_row_indices
        injected = data.injected_defect_rows
        tp, fp, fn = len(injected & quarantined_indices), len(quarantined_indices - injected), len(injected - quarantined_indices)
        detection = DefectDetectionMetrics(tp, fp, fn, tp / (tp + fp) if tp + fp else 1.0, tp / (tp + fn) if tp + fn else 1.0, len(quarantined_indices))
        clean_orders = data.work_orders.drop(index=list(quarantined_indices)).reset_index(drop=True)
        clean_for_validation = clean_orders.copy()
        clean_for_validation["ota_version"] = clean_for_validation["vehicle_id"].map(data.vehicles.set_index("vehicle_id")["ota_version"])
        publication_quality = evaluate_rules(clean_for_validation, rules, reference_tables={"vehicles": data.vehicles, "ota_releases": data.ota_releases})
        filtered_diagnostics = data.diagnostic_events[data.diagnostic_events["work_order_id"].isin(clean_orders["work_order_id"])]
        clean_data = WorkOrderDataset(clean_orders, data.vehicles, data.ota_releases, filtered_diagnostics, set())
        ingestion = ingest_generated_dataset(self.session, clean_data, version=dataset_version, rejected_rows=len(quarantined_indices))
        dq_run_id = f"DQR-{uuid4().hex[:12].upper()}"
        repository = DQRunRepository(self.session)
        repository.create(dq_run_id, dataset_version)
        rules_by_name = {rule.name: rule for rule in rules.rules}
        for row in source_quality.results.to_dict("records"):
            configured_rule = rules_by_name[row["rule_name"]]
            rule = self.session.scalar(select(models.DQRule).where(models.DQRule.name == row["rule_name"]))
            if rule is None:
                rule = models.DQRule(rule_id=f"RULE-{uuid4().hex[:12].upper()}", name=row["rule_name"], status=configured_rule.status, active_version=configured_rule.version)
                self.session.add(rule)
                self.session.flush()
            version = self.session.scalar(select(models.DQRuleVersion).where(models.DQRuleVersion.rule_id == rule.rule_id, models.DQRuleVersion.version == configured_rule.version))
            if version is None:
                version = models.DQRuleVersion(
                    rule_id=rule.rule_id, version=configured_rule.version, rule_type=configured_rule.type,
                    severity=configured_rule.severity, config=configured_rule.model_dump(mode="json"),
                    approved_at=datetime.now(timezone.utc),
                )
                self.session.add(version)
                self.session.flush()
            repository.add_result(dq_run_id, rule.rule_id, version.version_id, row["status"], int(row["failed_count"]), {"pass_rate": row["pass_rate"], "scope": str(row["scope"]), "error": row.get("error")})
        # Duplicate defects label both members of a duplicate pair, while the
        # quarantine policy intentionally retains the first/original record.
        # Use explicit effectiveness thresholds instead of requiring every
        # ground-truth row to be quarantined.
        detection_passed = detection.precision >= 0.80 and detection.recall >= 0.80
        repository.complete(dq_run_id, publication_quality.passed and detection_passed)
        persisted = int(self.session.scalar(select(func.count()).select_from(models.WorkOrder)) or 0)
        reconciliation = reconcile_counts(len(data.work_orders), len(quarantined_indices), persisted)
        sql_executor = SQLAssetExecutor(self.session, "sql")
        sql_executor.execute_marts()
        sql_validations = sql_executor.validate_platform(dataset_version)
        final_gate = publication_quality.passed and detection_passed and reconciliation.passed and all(sql_validations.values())
        self.session.flush()
        return PlatformRunSummary(ingestion, dq_run_id, source_quality.passed, detection_passed, publication_quality.passed, final_gate, detection, reconciliation, sql_validations)


def database_kpis(session: Session) -> dict[str, int]:
    return {
        "total_work_orders": int(session.scalar(select(func.count()).select_from(models.WorkOrder)) or 0),
        "ota_work_orders": int(session.scalar(select(func.count()).select_from(models.WorkOrder).where(models.WorkOrder.service_type == "OTA")) or 0),
        "open_backlog": int(session.scalar(select(func.count()).select_from(models.WorkOrder).where(models.WorkOrder.status.in_(["OPEN", "IN_PROGRESS"]))) or 0),
    }
