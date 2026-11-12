# Case study: durable AI retry safety

## Problem

Redis lease loss could be detected after a provider completed work. Returning HTTP 503 did not prove that provider cost, database changes, generated reviews, or Jira work had been rolled back. A blind client retry could invoke the provider twice.

## Reproduction

Deterministic workflows block inside the provider call while tests remove the real Redis lease. The first request returns a sanitized 503; the persisted operation becomes `AMBIGUOUS`; a retry is rejected without a second provider call. Separate PostgreSQL concurrency tests submit the same operation simultaneously and verify one durable operation and one provider execution.

## Root cause

A Redis concurrency lease controls admission but is not a durable request identity. Redis, PostgreSQL, and an external provider do not form one atomic distributed transaction, so HTTP failure alone cannot describe completion safely.

## Engineering solution

- Create a PostgreSQL operation claim before provider invocation.
- Scope uniqueness by principal, operation type, target resource, and `Idempotency-Key`.
- Bind the claim to a canonical request hash; conflicting payloads return 409.
- Use owner-token, `RUNNING`-only terminal updates so stale workers cannot overwrite completion.
- Replay a stored `SUCCEEDED` response without provider, review, or Jira duplication.
- Persist provider timeout or lost lease as `AMBIGUOUS`; never take it over automatically.
- Link persisted generated reviews and Jira idempotency to the stable operation ID.
- Expose owner-scoped `GET /api/v1/ai-operations/{operation_id}` for reconciliation.

## Test evidence

- PostgreSQL integration: 12 passed, zero skipped.
- Redis integration: 4 passed, zero skipped.
- [GitHub Actions run 43178347023](https://github.com/lichangqing1/automotive-work-order-intelligence/actions/runs/43178347023) completed successfully at commit `719a0bc`.

Sources and tests:

- [`ai_operations.py`](../../src/automotive_quality/application/ai_operations.py)
- [`v1.py`](../../src/automotive_quality/api/v1.py)
- [migration `20261112_0006`](../../migrations/versions/20261112_0006_ai_operation_idempotency.py)
- [`test_ai_operation_idempotency.py`](../../tests/test_ai_operation_idempotency.py)
- [`test_postgres_ai_operation_idempotency.py`](../../tests/integration/test_postgres_ai_operation_idempotency.py)
- [idempotency contract](../AI_OPERATION_IDEMPOTENCY.md)

## Before and after

Before: an ambiguous 503 could encourage a duplicate provider invocation.

After: the same logical request is durably claimed, successful results replay, ambiguous operations block automatic retry, and linked review/Jira records use stable identities.

## Remaining limitations

The platform does not promise exactly-once provider execution or billing across arbitrary crashes. A process can stop after provider acceptance but before durable completion, leaving `RUNNING`. Operators must reconcile provider, AI Run, review, and operation records before issuing a new key.
