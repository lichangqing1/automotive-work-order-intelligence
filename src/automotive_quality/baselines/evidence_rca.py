from __future__ import annotations

from automotive_quality.domains.ai.schemas import AIRootCauseAnalysis, RCAClaim
from automotive_quality.domains.evaluation.ai_value import EvidenceItem


def analyze_evidence(evidence: list[EvidenceItem]) -> AIRootCauseAnalysis:
    """Transparent rule baseline; it never reads benchmark labels."""
    text = " ".join(item.fact for item in evidence).casefold()
    ids = [item.id for item in evidence]
    rules = [
        ("OTA_COMPATIBILITY", "unsupported_software_version", ("supports ota versions", "attempted ota")),
        ("DATA_QUALITY", "missing_resolution_timestamp", ("status is resolved", "resolved_at is null")),
        ("REFERENTIAL_INTEGRITY", "orphan_vehicle_reference", ("references vehicle", "no vehicle")),
        ("STATUS_TRANSITION", "invalid_direct_transition", ("transition is open to closed", "permits open to in_progress")),
        ("TEMPORAL_CONSISTENCY", "resolution_before_creation", ("created_at", "resolved_at")),
        ("DUPLICATE_INGESTION", "missing_idempotency_enforcement", ("idempotency key", "two database rows")),
    ]
    for failure_class, cause, terms in rules:
        if all(term in text for term in terms):
            return AIRootCauseAnalysis(
                failure_class=failure_class, probable_root_causes=[cause], supporting_evidence=ids,
                recommended_checks=["Verify the cited facts against the authoritative source"], confidence=0.8,
                insufficient_evidence=False, claims=[RCAClaim(claim=cause, evidence_ids=ids)],
            )
    return AIRootCauseAnalysis(
        failure_class="INSUFFICIENT_EVIDENCE", probable_root_causes=[], supporting_evidence=[],
        recommended_checks=["Collect diagnostic events and versioned configuration evidence"],
        confidence=0.0, insufficient_evidence=True,
    )
