import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from automotive_quality.domains.evaluation.policy import Policy, evaluate_policies
from automotive_quality.domains.work_orders.reconciliation import reconcile_counts, reconcile_grouped_metrics
from automotive_quality.infrastructure.database import models
from automotive_quality.infrastructure.database.base import Base
from automotive_quality.infrastructure.database.sql_executor import SQLAssetExecutor


def test_count_reconciliation_pass_and_failure() -> None:
    assert reconcile_counts(100, 4, 96).passed
    failure = reconcile_counts(100, 4, 95)
    assert not failure.passed and failure.variance == -1


def test_grouped_reconciliation_catches_api_mismatch() -> None:
    sql = pd.DataFrame({"ota": ["6.2.1", "6.2.2"], "issues": [12, 8]})
    api = pd.DataFrame({"ota": ["6.2.1", "6.2.2"], "issues": [11, 8]})
    results = reconcile_grouped_metrics(sql, api, keys=["ota"], metric="issues")
    assert [item.passed for item in results] == [False, True]


def test_sql_reconciliation_uses_version_scoped_clean_snapshots() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(models.Dataset(dataset_id="DS-1", name="Regression dataset", source_type="test"))
        session.add(models.DatasetVersion(
            dataset_version_id="DSV-clean-v1", dataset_id="DS-1", version="clean-v1",
            row_count=2, content_hash="a" * 64,
        ))
        session.add_all([
            models.WorkOrderSnapshot(
                dataset_version_id="DSV-clean-v1", work_order_id=f"WO-{index}",
                payload={"work_order_id": f"WO-{index}"}, row_hash=str(index) * 64,
            )
            for index in (1, 2)
        ])
        session.flush()

        result = SQLAssetExecutor(session, "sql").run_validation(
            "source_target_reconciliation", {"dataset_version": "clean-v1"},
        )

        assert result == [{"expected_clean_count": 2, "actual_clean_count": 2}]


@pytest.mark.parametrize(("op", "threshold", "passed"), [(">=", 0.8, True), (">", 0.9, False), ("<=", 0.9, True), ("<", 0.9, False)])
def test_generic_policy_operators(op: str, threshold: float, passed: bool) -> None:
    result = evaluate_policies({"retrieval": {"recall": 0.9}}, [Policy(metric="retrieval.recall", operator=op, threshold=threshold)])
    assert result[0].passed is passed


def test_unknown_policy_operator_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported policy operator"):
        evaluate_policies({"metric": 1}, [Policy(metric="metric", operator="~=", threshold=1)])
