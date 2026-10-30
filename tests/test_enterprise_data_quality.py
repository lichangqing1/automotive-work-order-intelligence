from datetime import datetime, timezone

import pandas as pd
import pytest

from automotive_quality.domains.data_quality.models import DQRule, DQRuleSet, ManagedRule, RuleStatus
from automotive_quality.domains.data_quality.service import evaluate_rules


def _frame() -> pd.DataFrame:
    return pd.DataFrame({
        "id": ["WO-0000001", "bad", "WO-0000003"],
        "vehicle_id": ["V1", "MISSING", "V2"],
        "status": ["RESOLVED", "OPEN", "CLOSED"],
        "priority": ["P1", "PX", "P2"],
        "resolution": ["fixed", None, None],
        "resolved_at": ["2026-01-01", None, "2026-01-03"],
        "sla_hours": [24, 0, 200],
        "created_at": ["2025-12-31", "2026-01-02", "2026-01-04"],
    })


@pytest.mark.parametrize(("rule", "failed"), [
    (DQRule(name="allowed", type="allowed_values", column="priority", values=["P0", "P1", "P2", "P3"]), 1),
    (DQRule(name="range", type="range", column="sla_hours", min_value=1, max_value=168), 2),
    (DQRule(name="regex", type="regex", column="id", pattern=r"^WO-[0-9]{7}$"), 1),
    (DQRule(name="comparison", type="column_comparison", left="resolved_at", operator=">=", right="created_at"), 1),
])
def test_row_rule_operators(rule: DQRule, failed: int) -> None:
    result = evaluate_rules(_frame(), DQRuleSet(table="orders", rules=[rule]))
    assert int(result.results.iloc[0]["failed_count"]) == failed


def test_conditional_required_fields() -> None:
    rule = DQRule(name="resolved_fields", type="conditional_not_null", condition={"status": ["RESOLVED", "CLOSED"]}, columns=["resolution", "resolved_at"], severity="critical")
    result = evaluate_rules(_frame(), DQRuleSet(table="orders", rules=[rule]))
    assert result.failed_row_indices == {2}
    assert not result.passed


def test_foreign_key_uses_reference_table() -> None:
    rule = DQRule(name="vehicle_fk", type="foreign_key", column="vehicle_id", reference_table="vehicles", reference_column="vehicle_id")
    vehicles = pd.DataFrame({"vehicle_id": ["V1", "V2"]})
    result = evaluate_rules(_frame(), DQRuleSet(table="orders", rules=[rule]), reference_tables={"vehicles": vehicles})
    assert result.failed_row_indices == {1}


def test_missing_reference_table_is_explicit_error() -> None:
    rule = DQRule(name="vehicle_fk", type="foreign_key", column="vehicle_id", reference_table="vehicles", reference_column="vehicle_id")
    result = evaluate_rules(_frame(), DQRuleSet(table="orders", rules=[rule]))
    assert result.configuration_errors == ["vehicle_fk: MISSING_REFERENCE_TABLE: vehicles"]
    assert result.results.iloc[0]["status"] == "RULE_CONFIGURATION_ERROR"


def test_freshness_rule() -> None:
    frame = pd.DataFrame({"event_at": ["2026-01-01T00:00:00Z"]})
    rule = DQRule(name="fresh", type="freshness", scope="dataset", column="event_at", max_value=24)
    result = evaluate_rules(frame, DQRuleSet(table="events", rules=[rule]), now=datetime(2026, 1, 3, tzinfo=timezone.utc))
    assert result.failed_row_indices == set()
    assert result.dataset_failures == ["fresh"]


def test_rule_lifecycle_rejects_skipped_state() -> None:
    rule = DQRule(name="required", type="not_null", column="vehicle_id", status=RuleStatus.DRAFT)
    managed = ManagedRule(rule_id="DQ-1", name=rule.name, version=1, status=RuleStatus.DRAFT, rule=rule)
    with pytest.raises(ValueError, match="Invalid rule transition"):
        managed.transition(RuleStatus.ACTIVE)
    assert managed.transition(RuleStatus.REVIEWED).status == RuleStatus.REVIEWED
