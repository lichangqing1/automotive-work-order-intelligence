from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def test_evaluation_script_creates_output_directory_on_clean_checkout(tmp_path: Path, monkeypatch) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts/run_ai_evaluation.py"
    spec = importlib.util.spec_from_file_location("run_ai_evaluation", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "evaluate_mock_baseline", lambda _: {"accuracy": 1.0})
    monkeypatch.setattr(module, "evaluate_ai_policies", lambda *_: {"passed": True})

    module.main(tmp_path)

    output = tmp_path / "results/automotive/ai_evaluation.json"
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["quality_gates"]["passed"] is True
