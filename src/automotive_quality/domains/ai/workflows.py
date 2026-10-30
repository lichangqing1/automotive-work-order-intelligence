from __future__ import annotations

import hashlib
import json
import time
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from automotive_quality.infrastructure.database.repositories import AIRunRepository

from .prompts import PromptRegistry
from .providers.base import LLMProvider
from .schemas import (
    AIRootCauseAnalysis,
    GeneratedTestSuite,
    RequirementAnalysis,
    RuleDraft,
)

T = TypeVar("T", bound=BaseModel)


class AIWorkflowService:
    def __init__(self, provider: LLMProvider, repository: AIRunRepository | None = None, prompt_registry: PromptRegistry | None = None) -> None:
        self.provider = provider
        self.repository = repository
        self.prompts = prompt_registry or PromptRegistry()
        self.last_run_id: str | None = None

    def _run(self, task: str, prompt_version: str, user_prompt: str, response_model: type[T]) -> T:
        template = self.prompts.load(task, prompt_version)
        prompt = f"{template.system}\n\n{user_prompt}"
        start = time.perf_counter()
        run_id = f"AIR-{uuid4().hex[:12].upper()}"
        self.last_run_id = run_id
        try:
            result = self.provider.generate_structured(prompt=prompt, response_model=response_model)
        except Exception as exc:
            if self.repository:
                self.repository.save(
                    run_id=run_id, task_type=task, provider=self.provider.name, model=self.provider.model,
                    prompt_version=prompt_version, prompt_hash=template.content_hash,
                    input_hash=hashlib.sha256(user_prompt.encode()).hexdigest(), output={}, schema_valid=False,
                    status="FAILED", error_message=str(exc), latency_ms=(time.perf_counter() - start) * 1000,
                )
            raise
        if self.repository:
            self.repository.save(
                run_id=run_id, task_type=task, provider=self.provider.name, model=self.provider.model,
                prompt_version=prompt_version, prompt_hash=template.content_hash,
                input_hash=hashlib.sha256(user_prompt.encode()).hexdigest(), output=result.model_dump(mode="json"),
                schema_valid=True, status="SUCCEEDED", error_message=None,
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        return result

    def analyze_requirement(self, requirement: str) -> RequirementAnalysis:
        return self._run("requirement_analysis", "v1", f"Analyze this automotive QA requirement:\n{requirement}", RequirementAnalysis)

    def generate_tests(self, requirement: str, analysis: RequirementAnalysis, prompt_version: str = "v1") -> GeneratedTestSuite:
        prompt = f"Generate reviewed-required deterministic test specifications for: {requirement}\nAnalysis: {analysis.model_dump_json()}"
        return self._run("test_generation", prompt_version, prompt, GeneratedTestSuite)

    def generate_rule(self, requirement: str) -> RuleDraft:
        return self._run("dq_rule_generation", "v1", f"Draft a supported data-quality DSL rule for: {requirement}", RuleDraft)

    def analyze_rca(self, evidence: dict[str, Any], prompt_version: str = "v1") -> AIRootCauseAnalysis:
        prompt = "Analyze only the supplied evidence. Refuse when insufficient:\n" + json.dumps(evidence, default=str)
        return self._run("rca", prompt_version, prompt, AIRootCauseAnalysis)
