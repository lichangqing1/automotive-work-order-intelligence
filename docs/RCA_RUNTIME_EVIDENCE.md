# Runtime RCA evidence contract

Operational RCA requests use `RCAEvidenceRequest`, not the evaluation scorer.
Each request contains an optional request `case_id` and an `evidence_items`
array. Every item has:

- a non-empty stable `id` containing only letters, numbers, `.`, `_`, `:`, or
  `-`;
- non-blank `content` (`fact` remains accepted as an input alias for the
  versioned evaluation fixtures);
- an optional `case_id` matching the request case.

Evidence IDs must be unique within the request. Case-associated items require a
request case ID, and items from another case are rejected. Validation occurs
before the provider is called. Client validation errors contain field paths and
error types, but do not echo evidence content.

## Provider-output validation

Schema validity alone is not sufficient. Before an RCA run can be persisted as
`SUCCEEDED`, the workflow verifies that:

- every flat and claim-level evidence reference belongs to the authorized
  request set;
- neither flat nor per-claim reference lists contain duplicates;
- the flat reference set matches the union of claim-level references;
- each asserted root cause has a claim-level citation;
- assertions are not made when the request contains no evidence; and
- an explicit insufficient-evidence response contains no assertions or claimed
  supporting references.

Invalid provider output raises a typed `RCAProviderOutputError`, is never
returned as a grounded conclusion, and cannot be persisted as a successful AI
run. The API reports sanitized structured diagnostics with HTTP 502. Invalid
client evidence receives HTTP 422. Valid asserted output is marked
`evidence_reference_status: VALIDATED`; valid abstention is marked
`INSUFFICIENT_EVIDENCE`. All operational RCA output remains
`review_status: REVIEW_REQUIRED`.

## Persistence and external synchronization

Test-result failures are committed before optional RCA enrichment. Jira issue
creation and RCA comments occur only after runtime RCA validation succeeds. If
validation fails, the deterministic failure remains durable, the RCA run is not
linked as successful, and external synchronization is marked failed without
sending fabricated evidence.

Reference validation proves identity and request authorization only. It does
not prove that arbitrary generated prose is semantically entailed by a known
evidence item; that judgment remains part of human review.

The existing transaction boundary can roll back a failed AI-run audit row when
the caller rolls back after enrichment failure. Correcting that broader failed
audit persistence behavior is AUDIT-010 and is intentionally outside Phase A4.
