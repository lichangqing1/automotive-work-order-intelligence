import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_package_has_no_legacy_runtime_imports() -> None:
    violations = []
    for path in (ROOT / "src/automotive_quality").rglob("*.py"):
        if "baselines" in path.parts:
            continue
        text = path.read_text()
        if re.search(r"(?:from|import)\s+automotive(?:\.|\s|$)", text, re.MULTILINE):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_production_interfaces_have_no_sqlite_or_csv_fallbacks() -> None:
    violations = []
    for root in (ROOT / "src/automotive_quality", ROOT / "dashboard"):
        for path in root.rglob("*.py"):
            text = path.read_text()
            if any(token in text for token in ("sqlite3", "automotive_work_orders.sqlite", "work_order_features.csv")):
                violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_migration_baseline_is_explicit_and_immutable() -> None:
    revisions = sorted((ROOT / "migrations/versions").glob("*.py"))
    assert revisions[0].name == "20261015_0001_initial_explicit_schema.py"
    assert "20261016_0002_ai_value_evaluation.py" in {path.name for path in revisions}
    for revision in revisions:
        text = revision.read_text()
        assert "op.create_table" in text or "op.add_column" in text
        assert "Base.metadata" not in text
        assert "create_all" not in text
