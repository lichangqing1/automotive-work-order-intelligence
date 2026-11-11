# AI run failure-audit semantics

Every provider invocation receives a unique `AIR-*` run ID. Repeated attempts
for the same task and hashed input share a non-secret `correlation_id` but never
overwrite an earlier run.

AI run audit writes use a separate database connection and committed
transaction. Provider invocation and response-validation failures therefore
survive rollback of the calling business session. A successful provider result
is also audited before downstream business persistence; if that persistence
fails, the workflow changes the audit to `FAILED`, removes the stored output,
and records a sanitized business-persistence stage.

Failure records contain structured stage/category values, hashes rather than
prompts, an empty output, a generic sanitized message, latency, and completion
time. Raw exceptions, credentials, prompts, and provider payloads are not
stored for failed runs. Failed records are never successful or publishable;
generated tests remain `REVIEW_REQUIRED` under the existing review rules.

If the independent audit transaction itself fails, `AIRunAuditPersistenceError`
is raised. The workflow does not return provider output or claim success. The
exception message is fixed and sanitized; the underlying exception remains
available only through exception chaining for protected operational logging.

Jira synchronization remains a distinct post-business-commit boundary.
Provider failure, provider-output validation, human review state, Jira sync
failure, and Jira retry are not collapsed into one status.

Migration `20261111_0004` adds nullable failure stage, error category,
correlation ID, and completion timestamp columns. It does not rewrite existing
AI runs or historical evaluation artifacts.
