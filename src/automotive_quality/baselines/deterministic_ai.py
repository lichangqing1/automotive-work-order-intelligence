from __future__ import annotations

import re

from .schemas import DQRuleSpec, RCAResult, ResolutionResponse, SimilarCase, WorkOrderInput

CHECKS_BY_CATEGORY = {
    "OTA_FAILURE": ["Verify package checksum", "Check network and battery prerequisites", "Review update-agent logs"],
    "INFOTAINMENT": ["Verify IVI firmware version", "Inspect initialization logs", "Perform controlled head-unit reboot"],
    "CHARGING": ["Read BMS/OBC diagnostic codes", "Inspect charge-port sensors", "Reproduce on a known-good charger"],
    "HVAC": ["Run actuator calibration", "Check compressor telemetry", "Inspect controller software version"],
    "SENSOR": ["Inspect sensor alignment and contamination", "Run calibration procedure", "Review ADAS diagnostic logs"],
}


def assist_resolution(case: WorkOrderInput, similar: list[SimilarCase]) -> ResolutionResponse:
    """Evidence-first deterministic RAG response; an LLM can replace only this synthesis step."""
    if not similar or similar[0].score < 0.05:
        return ResolutionResponse(
            likely_issue="Insufficient historical evidence", evidence=[],
            recommended_checks=["Collect diagnostic logs", "Confirm software and hardware versions"],
            citations=[], confidence=0.0,
        )
    category_counts: dict[str, int] = {}
    for item in similar:
        category_counts[item.category] = category_counts.get(item.category, 0) + 1
    category = max(category_counts, key=category_counts.get)
    citations = [item.work_order_id for item in similar]
    evidence = [
        f"{len(similar)} retrieved historical cases",
        f"{category_counts[category]} of {len(similar)} cases classified as {category}",
        f"Best-match similarity is {similar[0].score:.2f} ({similar[0].work_order_id})",
    ]
    return ResolutionResponse(
        likely_issue=category.replace("_", " ").title(), evidence=evidence,
        recommended_checks=CHECKS_BY_CATEGORY.get(category, ["Review diagnostic evidence"]),
        citations=citations, confidence=round(min(0.95, similar[0].score * 0.75 + category_counts[category] / len(similar) * 0.25), 3),
    )


def build_rca(case: WorkOrderInput, similar: list[SimilarCase]) -> RCAResult:
    if not similar:
        return RCAResult(probable_root_causes=[], supporting_evidence=[], recommended_checks=["Collect additional evidence"], confidence=0)
    top = similar[0]
    same_category = sum(item.category == top.category for item in similar)
    causes = [f"Known {top.category.lower().replace('_', ' ')} pattern"]
    if case.ota_version:
        causes.append(f"Software compatibility issue around OTA {case.ota_version}")
    return RCAResult(
        probable_root_causes=causes,
        supporting_evidence=[f"{same_category}/{len(similar)} retrieved cases share category {top.category}", f"Top evidence: {top.work_order_id} at {top.score:.2f}"],
        recommended_checks=CHECKS_BY_CATEGORY.get(top.category, ["Inspect system logs"]),
        confidence=round(min(0.95, 0.5 * top.score + 0.5 * same_category / len(similar)), 3),
    )


def generate_rule(requirement: str) -> DQRuleSpec:
    """Create a reviewable rule draft without executing untrusted generated code."""
    lowered = requirement.lower()
    condition = {}
    if "resolved" in lowered:
        condition["status"] = "RESOLVED"
    if "ota" in lowered:
        condition["service_type"] = "OTA"
    known_fields = ["resolution", "resolved_at", "vehicle_id", "error_code", "description"]
    mentioned = [field for field in known_fields if field.replace("_", " ") in lowered or field in lowered]
    if "resolved time" in lowered and "resolved_at" not in mentioned:
        mentioned.append("resolved_at")
    if not mentioned and "resolution information" in lowered:
        mentioned = ["resolution", "resolved_at"]
    if not mentioned:
        mentioned = ["description"]
    checks = [{"field": field, "operator": "not_null"} for field in mentioned]
    name = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")[:48] or "generated_rule"
    return DQRuleSpec(rule_name=name, condition=condition, checks=checks)
