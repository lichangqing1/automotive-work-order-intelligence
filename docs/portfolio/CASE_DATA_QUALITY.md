# Case study: controlled data quality and reconciliation

## Problem

Automotive work orders combine vehicle identity, OTA compatibility, diagnostic evidence, status transitions, timestamps, and downstream operational metrics. A row can be individually valid yet inconsistent with its vehicle, release, or source totals.

## Reproduction and measurement

The synthetic adapter creates a deterministic 30,000-record benchmark and records the exact injected-defect row identities. The quality pipeline evaluates Python rules, SQL relationships, quarantine, and raw-minus-quarantined reconciliation. Detection is measured against known injected rows rather than inferred from the number of rule failures.

## Root cause addressed

Field-only checks cannot detect cross-table or lifecycle failures, and an aggregate “rules passed” count cannot establish detection accuracy. Earlier pipeline designs also risked mixing source rows, clean rows, and current projections without immutable dataset identity.

## Engineering solution

- Immutable `DatasetVersion` records and source fingerprints isolate every run.
- Typed DQ rules cover completeness, validity, conditional, temporal, foreign-key, regex, range, freshness, and aggregate checks.
- Failed rows enter quarantine before the clean layer.
- Reconciliation proves `raw − quarantined = clean` and compares grouped SQL/API results with variance evidence.
- Repeat-safe ingestion and independent attempt auditing preserve success and failure history.

## Evidence

| Controlled measurement | Result |
|---|---:|
| Synthetic work orders | 30,000 |
| Known injected-defect rows | 1,200 |
| Injected rows detected | 1,200 |
| False negatives in this benchmark | 0 |
| False positives against the injected-row oracle | 0 |

Sources and tests:

- [`synthetic.py`](../../src/automotive_quality/infrastructure/sources/synthetic.py)
- [`service.py`](../../src/automotive_quality/domains/data_quality/service.py)
- [`reconciliation.py`](../../src/automotive_quality/domains/work_orders/reconciliation.py)
- [`test_automotive_generator_quality.py`](../../tests/test_automotive_generator_quality.py)
- [`test_reconciliation_policy.py`](../../tests/test_reconciliation_policy.py)
- [`test_postgres_ingestion_retry.py`](../../tests/integration/test_postgres_ingestion_retry.py)

## Before and after

Before: isolated validation counts could not prove source-to-target consistency or distinguish detected injected defects from unrelated flags.

After: the controlled benchmark reports exact row-level TP/FP/FN evidence, quarantines failures, and reconciles persisted outputs under one dataset version.

## Limitations

The oracle covers deliberately injected synthetic defects. Zero FP/FN in this benchmark is not evidence of universal production accuracy, coverage of unknown defect classes, or compliance certification.
