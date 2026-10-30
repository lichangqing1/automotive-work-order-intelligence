from __future__ import annotations

import re

from automotive_quality.domains.ai.schemas import GeneratedTestCase, GeneratedTestSuite, TestDataEntry


def generate_template_tests(requirement: str) -> GeneratedTestSuite:
    """A reproducible, non-trivial baseline that never reads benchmark gold labels."""
    lowered = requirement.casefold()
    cases = [
        _case("BASE-POS", "Valid requirement behavior", "positive", requirement, "Supply valid data and verify the stated behavior."),
        _case("BASE-NEG", "Reject missing or invalid required data", "negative", requirement, "Remove or invalidate a required value and verify rejection."),
        _case("BASE-BND", "Validate the requirement boundary", "boundary", requirement, "Exercise equality and immediately adjacent boundary values."),
    ]
    if any(token in lowered for token in ("api", "database", "cross-table", "service")):
        cases.append(_case("BASE-INT", "Verify integration consistency", "integration", requirement, "Compare the persisted and exposed representations."))
    if any(token in lowered for token in ("must contain", "not null", "unique", "timestamp", "data")):
        cases.append(_case("BASE-DQ", "Verify persisted data quality", "data_quality", requirement, "Inspect persisted data for required constraints."))
    return GeneratedTestSuite(requirement=requirement, cases=cases)


def _case(test_id: str, title: str, category: str, requirement: str, expected: str) -> GeneratedTestCase:
    slug = re.sub(r"\s+", " ", requirement).strip()
    return GeneratedTestCase(
        test_id=test_id,
        title=title,
        objective=f"Validate: {slug}",
        preconditions=["A controlled test fixture exists"],
        test_data=[TestDataEntry(name="source", value="deterministic-template")],
        steps=["Arrange the described condition", "Execute the requirement behavior", "Observe the deterministic outcome"],
        expected_result=expected,
        category=category,
        priority="P1",
    )
