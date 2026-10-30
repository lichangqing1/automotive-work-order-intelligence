from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Query

from .ai import assist_resolution, build_rca, generate_rule
from .generator import generate_dataset
from .models import DQRuleSpec, RCAResult, ResolutionResponse, SimilarCase, WorkOrderInput
from .retrieval import CaseIndex

app = FastAPI(
    title="Automotive Work Order Intelligence API",
    version="1.0.0",
    description="Evidence-grounded retrieval, resolution assistance, RCA and governed rule drafting.",
)


@lru_cache(maxsize=1)
def get_index() -> CaseIndex:
    data_path = Path("data/processed/work_order_features.csv")
    if data_path.exists():
        frame = pd.read_csv(data_path)
    else:
        frame = generate_dataset(rows=2_000, seed=42, defect_rate=0).work_orders
    return CaseIndex.build(frame)


def _query(case: WorkOrderInput) -> str:
    return " ".join(filter(None, [case.category, case.error_code, case.description, case.ota_version]))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/cases/search", response_model=list[SimilarCase])
def search_cases(case: WorkOrderInput, top_k: int = Query(5, ge=1, le=20)) -> list[SimilarCase]:
    return get_index().search(_query(case), top_k=top_k)


@app.post("/assist/resolution", response_model=ResolutionResponse)
def resolution_assistant(case: WorkOrderInput, top_k: int = Query(5, ge=1, le=20)) -> ResolutionResponse:
    return assist_resolution(case, get_index().search(_query(case), top_k=top_k))


@app.post("/assist/rca", response_model=RCAResult)
def rca_assistant(case: WorkOrderInput, top_k: int = Query(5, ge=1, le=20)) -> RCAResult:
    return build_rca(case, get_index().search(_query(case), top_k=top_k))


@app.post("/quality/rules/draft", response_model=DQRuleSpec)
def draft_rule(requirement: str = Query(min_length=5)) -> DQRuleSpec:
    return generate_rule(requirement)

