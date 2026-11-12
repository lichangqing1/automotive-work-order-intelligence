# API security hardening

## Request and schema limits

The API enforces a bounded ASGI request gate before JSON parsing. The local
default is 1 MiB (`MAX_REQUEST_BODY_BYTES=1048576`). Both declared
`Content-Length` and bytes actually received are checked, so missing, smaller,
or chunked lengths do not bypass the limit. At most the configured limit is
buffered before parsing; larger streams are rejected as soon as they cross the
limit. Reverse proxies must set an equal or smaller body limit; the application
limit remains the backstop.

Request schemas independently bound identifiers, prompts, evidence, lists,
review text, and submitted results. Oversized bodies return 413; structurally
valid bodies that exceed field limits return 422. Values are rejected rather
than truncated.

## AI trust boundary

Provider workflows serialize caller, Jira, and evidence content into a labeled
untrusted JSON section. Trusted prompts explicitly direct the model to treat
embedded commands as data. This reduces instruction ambiguity but does not
eliminate semantic prompt injection. Structured schemas, exact RCA evidence-ID
validation, `REVIEW_REQUIRED` generated tests, and DRAFT-only rules remain the
authoritative controls. Raw prompts are not logged.

## Jira boundary and failures

Jira summaries, descriptions, comments, and idempotency identifiers pass an
explicit allowlist/length boundary. Control characters are removed and common
credential forms are replaced with `[REDACTED]`; overlong payloads are rejected
without contacting Jira. Jira receives plain ADF text nodes, not caller markup.

External failures are persisted and returned only as stable categories such as
`EXTERNAL_TIMEOUT` or `EXTERNAL_FAILURE`. Raw upstream messages, URLs,
credentials, and response bodies are not stored in `sync_error` or returned by
retry APIs. Detailed operational investigation belongs in access-controlled
infrastructure telemetry.

## Deployment policy

The base Compose file is for local development and intentionally publishes
PostgreSQL and Redis ports. Shared deployments must not publish those ports and
must place them on an internal network. They must set `ENVIRONMENT` to
`shared`, `staging`, or `production`, configure explicit trusted hosts, disable
docs (`API_DOCS_ENABLED=false`), and make read admission fail closed
(`RATE_LIMIT_READ_FAIL_OPEN=false`). Startup rejects wildcard trusted hosts,
credentialed wildcard CORS, enabled docs, missing authentication, or read
fail-open in those environments.

CORS is disabled by default. Explicit origins may be configured, but wildcard
origins cannot be combined with credentials. `/health/live` remains minimal and
public; `/health/ready` remains authenticated, authorized, and rate limited.
The legacy `automotive.api` module refuses to load outside local development.

## Durable AI operations and distributed-control limitation

Provider-backed routes create a durable operation claim before provider
invocation. The stable identity combines the authenticated principal,
operation type, target resource, and caller-supplied `Idempotency-Key`; a
canonical request hash prevents the key from being reused for different
content. A completed operation replays its stored response without invoking the
provider or recreating linked reviews and Jira synchronization records.

Lease loss and provider timeouts record the operation as `AMBIGUOUS` and return
a sanitized recovery response containing the operation identifier. Clients
must inspect the authenticated operation-status endpoint and must not
automatically retry `RUNNING`, `FAILED`, or `AMBIGUOUS` operations with a new
key. See [durable AI operation idempotency](AI_OPERATION_IDEMPOTENCY.md) for the
state and reconciliation rules.

These controls prevent duplicate application execution under the tested retry
and concurrency conditions, but they do not guarantee exactly-once provider
execution or billing across arbitrary process or network failure. Provider
work may have completed before the application can durably record the outcome,
and PostgreSQL, Redis, and external providers do not share one transaction.

## Security events and dependencies

Authentication failure, authorization denial, quota rejection, lease loss,
review decisions, and external-sync failure emit structured security-event
fields. Principal IDs are represented by short SHA-256 digests. Bearer tokens,
prompts, database URLs, and provider secrets are excluded.

CI installs the project with both `dev` and `security` extras before running
`pip-audit`, so the scan covers installed runtime and development dependencies.
Dependabot monitors Python, Docker, and GitHub Actions dependencies. This
project uses bounded dependency ranges but does not yet commit a fully resolved
Python lock file; reproducible release builds should add hash-pinned constraints
and generate an SBOM in a later delivery phase.
