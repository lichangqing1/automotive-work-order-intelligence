# Case study: RCA metric integrity

## Problem

The preserved RCA v1 report showed 94.52% AI evidence support even though root-cause accuracy was 0%. That combination was mathematically possible under v1 but misleading as a portfolio claim.

## Reproduction and measurement

The same immutable RCA outputs and all 90/90 human reviews were rescored with `rca-metrics-v2`. Test-generation review completeness (1,122/1,122) and human-only measurements (30/30) were independently rechecked. No source experiment, review, threshold, or historical report was rewritten.

## Root cause

V1 treated evidence correctness and claim support as the same citation-level ratio. It could award favorable evidence scores when structured claims were omitted, count repeated IDs, and treat an incorrect root-cause assertion as supported when it cited an ID associated with the expected cause. Root-cause identity also allowed unsafe substring overlap.

Citation validity, evidence correctness, and claim support answer different questions:

- **Citation validity:** does the cited ID exist in this case?
- **Evidence correctness:** is the ID in the human-authored supporting set?
- **Evidence support:** does every asserted claim have correct support, including a matching root-cause identity?

## Engineering solution

`rca-metrics-v2` uses normalized exact labels or benchmark-declared equivalents, distinct claim-level numerators, unique evidence references, zero support for unsupported root-cause assertions, and explicit abstention behavior.

## Before and after

| AI RCA metric | Historical v1 | Corrected v2 |
|---|---:|---:|
| Citation validity | 100.00% | 90.00% |
| Evidence correctness | 94.52% | 84.52% |
| Evidence support | 94.52% | **13.33%** |
| Unsupported claims | 5.48% | **76.67%** |
| Root-cause accuracy | 0% | **0%** |
| Policy | BLOCK | **BLOCK** |

Sources and tests:

- [RCA v2 comparison](../reports/RCA_METRIC_INTEGRITY_V2_COMPARISON.md)
- [Versioned portfolio metric record](data/rca_metrics_v2.json)
- [`ai_value.py`](../../src/automotive_quality/domains/evaluation/ai_value.py)
- [`test_rca_metric_integrity.py`](../../tests/test_rca_metric_integrity.py)
- [`test_ai_value_review_completeness.py`](../../tests/test_ai_value_review_completeness.py)

## Remaining limitations

The corrected metrics validate curated evidence-ID relationships, not arbitrary prose entailment. Human review is still required for semantic support. The policy thresholds remain `proposed_until_calibrated`, and both the historical and corrected policies remain `BLOCK`.
