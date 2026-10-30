from pathlib import Path

import yaml

from .models import DQRuleSet


def load_rules(path: str | Path) -> DQRuleSet:
    with Path(path).open(encoding="utf-8") as handle:
        return DQRuleSet.model_validate(yaml.safe_load(handle))

