# API rate limiting and AI concurrency

All authenticated operations use shared Redis state keyed by a SHA-256 digest
of the authenticated principal ID. Bearer tokens, credential IDs, request
headers, and caller-supplied roles are never used in Redis keys. Authorization
remains a separate policy and runs before admission control.

## Initial policy

| Category | Default | Routes |
|---|---:|---|
| Paid provider AI | 10/minute/principal | `/ai/*`, persisted requirement analysis and generation |
| Jira/external sync | 10/minute/principal | Jira import, review sync, external-sync retry |
| Mutations | 30/minute/principal | review start/assessment/decision and test-result submission |
| Reads | 120/minute/principal | retrieval, datasets, metrics, runs, review/traceability/evaluation reads, readiness |

Deterministic baseline assistants share the AI request quota but do not consume
paid-provider concurrency. Authorized attempts are charged even when later
request validation or business execution fails. Administrators receive the
same limits as every other principal. Public `/health/live` is exempt.

The limiter uses a Redis-server-time fixed window and atomic `INCR`/`PEXPIRE`
Lua script. Routes in one category share a counter. A rejection returns `429`
with `Retry-After`; expired keys are removed by Redis TTL cleanup.

## AI concurrency

Paid provider endpoints admit at most two concurrent operations per principal.
A Redis sorted set stores an unguessable per-request lease token and expiry.
Atomic Lua scripts prune interrupted leases and admit only below capacity. A
heartbeat renews a live lease, and release removes only the caller's token.
Every normal return, validation failure, provider exception, and request
cancellation executes dependency cleanup. A worker termination is recovered
when its bounded lease expires. If heartbeat renewal loses the lease during a
normally completed provider operation, the API suppresses the successful
response and returns a sanitized `503` instead of claiming protected execution.

One API request is one concurrent provider operation even if the provider
performs internal transport retries. Current workflows make one logical
provider call per admitted request.

Provider operations additionally use durable PostgreSQL idempotency claims.
Successful replays still pass authentication, authorization, AI quota, and
concurrency admission before the stored response is returned. See
[durable AI operation idempotency](AI_OPERATION_IDEMPOTENCY.md).

## Redis failure policy

AI, Jira, review/test mutations, and external sync fail closed with sanitized
`503` responses when Redis admission cannot be verified. Low-cost reads use the
documented `RATE_LIMIT_READ_FAIL_OPEN=true` availability policy; set it to
`false` for deployments that require universal fail-closed admission. There is
no process-local fallback.

All values are environment configurable (see `.env.example`). Shared
deployments should use a deployment-specific namespace and a highly available,
authenticated Redis URL. Tests must use `REDIS_TEST_URL` and a unique namespace;
they never flush a shared Redis database.
