from __future__ import annotations

import numpy as np

from .ai import assist_resolution
from .models import WorkOrderInput
from .retrieval import CaseIndex


def evaluate_rag_assistance(index: CaseIndex, sample_size: int = 50, seed: int = 42) -> dict[str, float]:
    """Execute grounded-assistance cases and measure citations and unsupported responses."""
    sample = index.cases.sample(min(sample_size, len(index.cases)), random_state=seed)
    citation_checks: list[float] = []
    unsupported_checks: list[float] = []
    for _, row in sample.iterrows():
        query = f"{row['error_code']} {row['description']}"
        retrieved = index.search(query, top_k=5, exclude_id=str(row["work_order_id"]))
        request = WorkOrderInput(
            vehicle_model="unknown",
            description=str(row["description"]),
            error_code=str(row["error_code"]),
            category=str(row["category"]),
        )
        response = assist_resolution(request, retrieved)
        retrieved_ids = {item.work_order_id for item in retrieved}
        citation_checks.append(float(bool(response.citations) and set(response.citations) <= retrieved_ids))
        makes_claim = response.likely_issue != "Insufficient historical evidence"
        unsupported = makes_claim and (not response.citations or not response.evidence)
        unsupported_checks.append(float(unsupported))
    return {
        "citation_validity": float(np.mean(citation_checks)) if citation_checks else 0.0,
        "unsupported_claim_rate": float(np.mean(unsupported_checks)) if unsupported_checks else 0.0,
    }

