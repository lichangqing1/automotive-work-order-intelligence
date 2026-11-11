from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from automotive_quality.infrastructure.database.repositories import AIRunRepository

from .prompts import PromptRegistry
from .providers.base import LLMProvider
from .schemas import (
    AIRootCauseAnalysis,
    GeneratedTestSuite,
    RCAEvidenceRequest,
    RequirementAnalysis,
    RuleDraft,
)

T = TypeVar("T", bound=BaseModel)


class RCAProviderError(RuntimeError):
    def __init__(self, code: str, message: str, diagnostics: list[dict[str, object]] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics or []


class RCAProviderOutputError(RCAProviderError):
    pass


class RCAProviderFailure(RCAProviderError):
    pass


class RCAEvidenceValidationError(ValueError):
    def __init__(self, diagnostics: list[dict[str, object]]) -> None:
        super().__init__("RCA evidence request is invalid")
        self.code = "INVALID_RCA_EVIDENCE"
        self.diagnostics = diagnostics


class AIWorkflowService:
    def __init__(self, provider: LLMProvider, repository: AIRunRepository | None = None, prompt_registry: PromptRegistry | None = None) -> None:
        self.provider = provider
        self.repository = repository
        self.prompts = prompt_registry or PromptRegistry()
        self.last_run_id: str | None = None

    def _run(
        self,
        task: str,
        prompt_version: str,
        user_prompt: str,
        response_model: type[T],
        result_validator: Callable[[T], T] | None = None,
    ) -> T:
        template = self.prompts.load(task, prompt_version)
        prompt = f"{template.system}\n\n{user_prompt}"
        start = time.perf_counter()
        run_id = f"AIR-{uuid4().hex[:12].upper()}"
        self.last_run_id = run_id
        try:
            result = self.provider.generate_structured(prompt=prompt, response_model=response_model)
            if result_validator:
                result = result_validator(result)
        except Exception as exc:
            if self.repository:
                self.repository.save(
                    run_id=run_id, task_type=task, provider=self.provider.name, model=self.provider.model,
                    prompt_version=prompt_version, prompt_hash=template.content_hash,
                    input_hash=hashlib.sha256(user_prompt.encode()).hexdigest(), output={},
                    schema_valid=isinstance(exc, RCAProviderOutputError), status="FAILED",
                    error_message=_safe_failure_message(exc),
                    latency_ms=(time.perf_counter() - start) * 1000,
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

    def analyze_rca(
        self,
        evidence: RCAEvidenceRequest | dict[str, Any],
        prompt_version: str = "v1",
    ) -> AIRootCauseAnalysis:
        try:
            request = (
                evidence
                if isinstance(evidence, RCAEvidenceRequest)
                else RCAEvidenceRequest.model_validate(evidence)
            )
        except ValidationError as exc:
            raise RCAEvidenceValidationError([
                {
                    "field": ".".join(str(part) for part in error["loc"]),
                    "issue": error["type"],
                }
                for error in exc.errors(include_input=False, include_url=False)
            ]) from exc
        prompt = (
            "Analyze only the supplied evidence. Every factual claim must cite authorized "
            "evidence IDs. Refuse when insufficient:\n"
            + request.model_dump_json()
        )
        try:
            return self._run(
                "rca",
                prompt_version,
                prompt,
                AIRootCauseAnalysis,
                lambda result: _validate_rca_output(request, result),
            )
        except RCAProviderOutputError:
            raise
        except Exception as exc:
            raise RCAProviderFailure(
                "RCA_PROVIDER_FAILURE",
                "RCA provider failed to produce a valid structured response",
                [{"failure_type": type(exc).__name__}],
            ) from exc


def _validate_rca_output(
    request: RCAEvidenceRequest,
    result: AIRootCauseAnalysis,
) -> AIRootCauseAnalysis:
    authorized_ids = {item.id for item in request.evidence_items}
    assertions_present = bool(result.probable_root_causes or result.claims)

    if result.insufficient_evidence:
        if result.supporting_evidence:
            raise _rca_output_error(
                "ABSTENTION_WITH_EVIDENCE_REFERENCES",
                "insufficient-evidence output must not claim supporting evidence",
                [{"field": "supporting_evidence"}],
            )
        return result.model_copy(update={"evidence_reference_status": "INSUFFICIENT_EVIDENCE"})

    if not assertions_present:
        raise _rca_output_error(
            "EMPTY_RCA_CONCLUSION",
            "provider output must assert a supported conclusion or explicitly abstain",
        )
    if not authorized_ids:
        raise _rca_output_error(
            "ASSERTION_WITHOUT_INPUT_EVIDENCE",
            "root-cause assertions require authorized input evidence",
        )
    if result.probable_root_causes and len(result.claims) < len(result.probable_root_causes):
        raise _rca_output_error(
            "ROOT_CAUSE_WITHOUT_CLAIM_CITATION",
            "every asserted root cause requires a claim-level evidence citation",
        )

    diagnostics: list[dict[str, object]] = []
    if len(result.supporting_evidence) != len(set(result.supporting_evidence)):
        diagnostics.append({"field": "supporting_evidence", "issue": "duplicate_reference"})
    unknown_supporting = set(result.supporting_evidence) - authorized_ids
    if unknown_supporting:
        diagnostics.append({
            "field": "supporting_evidence",
            "issue": "unknown_evidence_reference",
            "count": len(unknown_supporting),
        })

    claim_ids: set[str] = set()
    for index, claim in enumerate(result.claims):
        unique_ids = set(claim.evidence_ids)
        if len(unique_ids) != len(claim.evidence_ids):
            diagnostics.append({
                "field": f"claims[{index}].evidence_ids",
                "issue": "duplicate_reference",
            })
        unknown_claim_ids = unique_ids - authorized_ids
        if unknown_claim_ids:
            diagnostics.append({
                "field": f"claims[{index}].evidence_ids",
                "issue": "unknown_evidence_reference",
                "count": len(unknown_claim_ids),
            })
        claim_ids.update(unique_ids)

    if set(result.supporting_evidence) != claim_ids:
        diagnostics.append({"field": "supporting_evidence", "issue": "claim_reference_mismatch"})
    if diagnostics:
        raise _rca_output_error(
            "INVALID_EVIDENCE_REFERENCES",
            "provider output contains unknown evidence or ambiguous evidence references",
            diagnostics,
        )
    return result.model_copy(update={"evidence_reference_status": "VALIDATED"})


def _rca_output_error(
    code: str,
    message: str,
    diagnostics: list[dict[str, object]] | None = None,
) -> RCAProviderOutputError:
    return RCAProviderOutputError(code, message, diagnostics)


def _safe_failure_message(exc: Exception) -> str:
    if isinstance(exc, RCAProviderError):
        return f"{exc.code}: {exc}"
    return f"{type(exc).__name__}: structured provider execution failed"
