from __future__ import annotations

import pytest

from automotive_quality.domains.ai.schemas import AIRootCauseAnalysis, RCAClaim
from automotive_quality.domains.evaluation.ai_value import RCA_METRIC_VERSION, RCACase, rca_metrics


def _case(
    *,
    ground_truth: str | None = "unsupported_software_version",
    evidence_sufficient: bool = True,
    equivalents: list[str] | None = None,
) -> RCACase:
    return RCACase(
        case_id="RCA-METRIC",
        failure_class="OTA_COMPATIBILITY",
        ground_truth_root_cause=ground_truth,
        equivalent_root_causes=equivalents or [],
        evidence_sufficient=evidence_sufficient,
        evidence=[
            {"id": "EV-SUPPORT", "fact": "Hardware supports versions through 6.1."},
            {"id": "EV-OTHER", "fact": "The battery is fully charged."},
            {"id": "EV-CONTRA", "fact": "Version 6.2 is recorded as compatible."},
        ],
        supporting_evidence_ids=["EV-SUPPORT"] if evidence_sufficient else [],
    )


def _result(
    cause: str | None,
    *,
    claims: list[RCAClaim] | None = None,
    supporting_evidence: list[str] | None = None,
    insufficient: bool = False,
    failure_class: str = "OTA_COMPATIBILITY",
) -> AIRootCauseAnalysis:
    causes = [cause] if cause is not None else []
    return AIRootCauseAnalysis(
        failure_class=failure_class,
        probable_root_causes=causes,
        supporting_evidence=supporting_evidence if supporting_evidence is not None else (
            ["EV-SUPPORT"] if causes else []
        ),
        recommended_checks=[],
        confidence=0.8,
        insufficient_evidence=insufficient,
        claims=claims or [],
    )


def test_rca_metric_contract_is_explicitly_versioned() -> None:
    assert RCA_METRIC_VERSION == "rca-metrics-v2"


def test_exact_root_cause_match_with_valid_support() -> None:
    result = _result(
        "Unsupported Software Version",
        claims=[RCAClaim(claim="unsupported_software_version", evidence_ids=["EV-SUPPORT"])],
    )
    assert rca_metrics(_case(), result) == {
        "failure_class_accuracy": 1.0,
        "root_cause_accuracy": 1.0,
        "citation_validity_rate": 1.0,
        "evidence_support_rate": 1.0,
        "evidence_correctness_rate": 1.0,
        "unsupported_claim_rate": 0.0,
        "correct_abstention": 0.0,
    }


def test_generic_substring_does_not_match_root_cause() -> None:
    metrics = rca_metrics(_case(), _result("version"))
    assert metrics["root_cause_accuracy"] == 0.0
    assert metrics["citation_validity_rate"] == 0.0
    assert metrics["evidence_support_rate"] == 0.0
    assert metrics["evidence_correctness_rate"] == 0.0
    assert metrics["unsupported_claim_rate"] == 1.0


def test_near_match_paraphrase_is_not_an_implicit_equivalence() -> None:
    result = _result(
        "software_version_not_supported",
        claims=[RCAClaim(claim="software_version_not_supported", evidence_ids=["EV-SUPPORT"])],
    )
    assert rca_metrics(_case(), result)["root_cause_accuracy"] == 0.0


def test_curated_equivalent_root_cause_is_accepted() -> None:
    result = _result(
        "software_version_not_supported",
        claims=[RCAClaim(claim="software_version_not_supported", evidence_ids=["EV-SUPPORT"])],
    )
    metrics = rca_metrics(_case(equivalents=["software version not supported"]), result)
    assert metrics["root_cause_accuracy"] == 1.0
    assert metrics["evidence_support_rate"] == 1.0


def test_correct_root_cause_without_claim_citations_is_unsupported() -> None:
    metrics = rca_metrics(_case(), _result("unsupported_software_version"))
    assert metrics["root_cause_accuracy"] == 1.0
    assert metrics["citation_validity_rate"] == 0.0
    assert metrics["evidence_correctness_rate"] == 0.0
    assert metrics["evidence_support_rate"] == 0.0
    assert metrics["unsupported_claim_rate"] == 1.0


def test_incorrect_root_cause_is_not_supported_by_a_correct_looking_citation() -> None:
    result = _result(
        "battery_voltage_drop",
        claims=[RCAClaim(claim="battery_voltage_drop", evidence_ids=["EV-SUPPORT"])],
    )
    metrics = rca_metrics(_case(), result)
    assert metrics["root_cause_accuracy"] == 0.0
    assert metrics["citation_validity_rate"] == 1.0
    assert metrics["evidence_correctness_rate"] == 1.0
    assert metrics["evidence_support_rate"] == 0.0
    assert metrics["unsupported_claim_rate"] == 1.0


def test_unrelated_known_evidence_is_valid_but_not_correct_or_supporting() -> None:
    result = _result(
        "unsupported_software_version",
        claims=[RCAClaim(claim="unsupported_software_version", evidence_ids=["EV-OTHER"])],
    )
    metrics = rca_metrics(_case(), result)
    assert metrics["citation_validity_rate"] == 1.0
    assert metrics["evidence_correctness_rate"] == 0.0
    assert metrics["evidence_support_rate"] == 0.0
    assert metrics["unsupported_claim_rate"] == 1.0


def test_contradictory_known_evidence_is_not_counted_as_support() -> None:
    result = _result(
        "unsupported_software_version",
        claims=[RCAClaim(claim="unsupported_software_version", evidence_ids=["EV-CONTRA"])],
    )
    metrics = rca_metrics(_case(), result)
    assert metrics["citation_validity_rate"] == 1.0
    assert metrics["evidence_correctness_rate"] == 0.0
    assert metrics["evidence_support_rate"] == 0.0


def test_invalid_evidence_ids_are_neither_valid_correct_nor_supporting() -> None:
    result = _result(
        "unsupported_software_version",
        claims=[RCAClaim(claim="unsupported_software_version", evidence_ids=["EV-UNKNOWN"])],
    )
    metrics = rca_metrics(_case(), result)
    assert metrics["citation_validity_rate"] == 0.0
    assert metrics["evidence_correctness_rate"] == 0.0
    assert metrics["evidence_support_rate"] == 0.0
    assert metrics["unsupported_claim_rate"] == 1.0


def test_duplicate_evidence_references_do_not_inflate_scores() -> None:
    result = _result(
        "unsupported_software_version",
        claims=[RCAClaim(
            claim="unsupported_software_version",
            evidence_ids=["EV-SUPPORT", "EV-SUPPORT", "EV-OTHER"],
        )],
    )
    metrics = rca_metrics(_case(), result)
    assert metrics["citation_validity_rate"] == 1.0
    assert metrics["evidence_correctness_rate"] == 0.5
    assert metrics["evidence_support_rate"] == 1.0
    assert metrics["unsupported_claim_rate"] == 0.0


def test_multiple_claims_report_mixed_support_exactly() -> None:
    result = _result(
        "unsupported_software_version",
        claims=[
            RCAClaim(claim="unsupported_software_version", evidence_ids=["EV-SUPPORT"]),
            RCAClaim(claim="Battery state caused the failure", evidence_ids=["EV-OTHER"]),
        ],
    )
    metrics = rca_metrics(_case(), result)
    assert metrics["citation_validity_rate"] == 1.0
    assert metrics["evidence_correctness_rate"] == 0.5
    assert metrics["evidence_support_rate"] == 0.5
    assert metrics["unsupported_claim_rate"] == 0.5


def test_appropriate_no_claim_abstention_has_explicit_vacuous_scores() -> None:
    result = _result(None, insufficient=True, failure_class="INSUFFICIENT EVIDENCE")
    assert rca_metrics(_case(ground_truth=None, evidence_sufficient=False), result) == {
        "failure_class_accuracy": 0.0,
        "root_cause_accuracy": 0.0,
        "citation_validity_rate": 1.0,
        "evidence_support_rate": 1.0,
        "evidence_correctness_rate": 1.0,
        "unsupported_claim_rate": 0.0,
        "correct_abstention": 1.0,
    }


def test_insufficient_evidence_with_speculation_is_not_an_abstention() -> None:
    result = _result(
        "network_timeout",
        claims=[RCAClaim(claim="network_timeout", evidence_ids=["EV-OTHER"])],
    )
    metrics = rca_metrics(_case(ground_truth=None, evidence_sufficient=False), result)
    assert metrics["root_cause_accuracy"] == 0.0
    assert metrics["evidence_support_rate"] == 0.0
    assert metrics["unsupported_claim_rate"] == 1.0
    assert metrics["correct_abstention"] == 0.0


def test_missing_ground_truth_never_awards_root_cause_accuracy() -> None:
    result = _result(
        "unsupported_software_version",
        claims=[RCAClaim(claim="unsupported_software_version", evidence_ids=["EV-SUPPORT"])],
    )
    assert rca_metrics(
        _case(
            ground_truth=None,
            evidence_sufficient=True,
            equivalents=["unsupported_software_version"],
        ),
        result,
    )["root_cause_accuracy"] == 0.0


def test_extra_incorrect_root_cause_prevents_identity_success() -> None:
    result = AIRootCauseAnalysis(
        failure_class="OTA_COMPATIBILITY",
        probable_root_causes=["unsupported_software_version", "battery_voltage_drop"],
        supporting_evidence=["EV-SUPPORT"],
        recommended_checks=[],
        confidence=0.8,
        insufficient_evidence=False,
        claims=[
            RCAClaim(claim="unsupported_software_version", evidence_ids=["EV-SUPPORT"]),
            RCAClaim(claim="battery_voltage_drop", evidence_ids=["EV-SUPPORT"]),
        ],
    )

    metrics = rca_metrics(_case(), result)

    assert metrics["root_cause_accuracy"] == 0.0
    assert metrics["evidence_support_rate"] == 0.0
    assert metrics["unsupported_claim_rate"] == 1.0


@pytest.mark.parametrize(
    ("failure_class", "expected"),
    [("ota compatibility", 1.0), ("compatibility", 0.0)],
)
def test_failure_class_uses_normalized_exact_matching(failure_class: str, expected: float) -> None:
    result = _result(
        "unsupported_software_version",
        claims=[RCAClaim(claim="unsupported_software_version", evidence_ids=["EV-SUPPORT"])],
        failure_class=failure_class,
    )
    assert rca_metrics(_case(), result)["failure_class_accuracy"] == expected
