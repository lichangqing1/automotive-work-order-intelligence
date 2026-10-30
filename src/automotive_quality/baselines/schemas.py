from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkOrderInput(BaseModel):
    vehicle_model: str
    ota_version: str | None = None
    description: str = Field(min_length=3)
    error_code: str | None = None
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    category: str | None = None


class SimilarCase(BaseModel):
    work_order_id: str
    score: float = Field(ge=0, le=1)
    category: str
    description: str
    resolution: str | None = None


class RCAResult(BaseModel):
    probable_root_causes: list[str]
    supporting_evidence: list[str]
    recommended_checks: list[str]
    confidence: float = Field(ge=0, le=1)


class ResolutionResponse(BaseModel):
    likely_issue: str
    evidence: list[str]
    recommended_checks: list[str]
    citations: list[str]
    confidence: float = Field(ge=0, le=1)


class DQRuleSpec(BaseModel):
    rule_name: str
    condition: dict[str, Any] = Field(default_factory=dict)
    checks: list[dict[str, Any]]
    status: Literal["pending_approval"] = "pending_approval"


class PipelineSummary(BaseModel):
    run_id: str
    generated_at: datetime
    raw_rows: int
    clean_rows: int
    injected_defects: int
    detected_defect_rows: int
    detection_rate: float
    quality_passed: bool
