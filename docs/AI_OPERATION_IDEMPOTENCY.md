# Durable AI operation idempotency

Provider-backed API operations accept an `Idempotency-Key` header. Keys must be
8–128 characters and contain only letters, digits, `.`, `_`, `:`, or `-`.
Callers must generate one stable key for a logical operation and reuse that key
for status recovery or response replay. Shared, staging, and production
deployments reject provider operations without a key. Local development keeps
legacy keyless behavior for compatibility, but keyless calls have no retry
guarantee.

The durable scope is the authenticated principal, operation type, target
resource, and key. A SHA-256 digest of canonical request JSON binds the claim to
its content. Raw bearer credentials and raw request payloads are not stored.
Another principal cannot replay or inspect the operation. Reusing a scoped key
with different content returns `409 IDEMPOTENCY_KEY_CONFLICT`.

## States and HTTP behavior

| State | Same-key request behavior |
|---|---|
| `RUNNING` | `409 OPERATION_IN_PROGRESS`; do not start another provider call |
| `SUCCEEDED` | Replay the durable response with `Idempotent-Replay: true` |
| `FAILED` | `409 OPERATION_FAILED`; use a new key only after deciding a new logical attempt is safe |
| `AMBIGUOUS` | `409 OPERATION_AMBIGUOUS`; never retry automatically |

The first successful response includes `X-AI-Operation-ID`. Error responses for
ambiguous completion include the operation ID in the structured body. An
authenticated caller can query `GET /api/v1/ai-operations/{operation_id}`.
Status responses expose state and correlation identifiers, not stored response
content or raw provider errors. Status lookup and successful replay consume the
normal read and AI quota respectively.

The provider call still cannot be made exactly once across an arbitrary process
or network failure when the provider lacks native idempotency and execution
lookup. A process interruption after provider execution can leave `RUNNING`;
lease loss or a provider timeout becomes `AMBIGUOUS`. Neither state is taken
over automatically. Operators must inspect the durable AI run, linked review,
and provider records before deciding whether a new operation key is safe.

Persisted test generation links its review batch and Jira idempotency key to the
stable operation ID. Lease health is checked after provider output and again
before Jira synchronization. These checks prevent a worker already known to
have lost its lease from starting later side effects, but PostgreSQL and Redis
do not form one distributed transaction.

Retain `RUNNING` and `AMBIGUOUS` records until reconciliation. Retain terminal
`SUCCEEDED` and `FAILED` records for at least the longest client retry and audit
window (recommended minimum: 30 days). Any cleanup job must delete only
terminal records older than the approved retention period and must preserve
referenced review and AI audit evidence.
