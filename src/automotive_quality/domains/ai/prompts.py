from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PromptTemplate:
    task: str
    version: str
    system: str
    content_hash: str


class PromptRegistry:
    """Loads immutable, versioned prompts from the repository prompt catalog."""

    def __init__(self, root: str | Path = "prompts") -> None:
        self.root = Path(root)

    def load(self, task: str, version: str = "v1") -> PromptTemplate:
        path = self.root / task / f"{version}.yaml"
        raw = path.read_bytes()
        document = yaml.safe_load(raw)
        if document.get("version") != version or not document.get("system"):
            raise ValueError(f"Invalid prompt template: {path}")
        return PromptTemplate(task, version, str(document["system"]), hashlib.sha256(raw).hexdigest())
