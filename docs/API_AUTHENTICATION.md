# API bearer authentication

All `/api/v1` routes and `/health/ready` require a configured bearer credential.
`/health/live` remains public and performs no dependency checks. The API fails
closed: missing or invalid credentials receive `401`, while a missing or invalid
server authentication configuration makes protected routes unavailable with a
generic `503` response. Shared, staging, and production settings reject missing
or structurally invalid authentication configuration during application startup.

## Credential generation and configuration

Generate a high-entropy token in a protected operator shell and calculate its
SHA-256 digest without recording the token in shell history, source control, or
logs. Python's `secrets.token_urlsafe(32)` is an appropriate generator. Deliver
the raw token through the deployment secret manager only to the server-side
caller, such as the Streamlit process. Configure the API with JSON containing
only the digest:

```json
[
  {
    "principal_id": "dashboard-service",
    "category": "service",
    "roles": ["reader"],
    "credentials": [
      {
        "key_id": "2026-11-a",
        "token_sha256": "<64-character SHA-256 hex digest>",
        "enabled": true,
        "expires_at": "2027-02-01T00:00:00Z"
      }
    ]
  }
]
```

Set that JSON as `API_AUTH_PRINCIPALS_JSON`. Set the corresponding raw token as
`API_BEARER_TOKEN` only in the Streamlit server environment. A caller sends it
as `Authorization: Bearer <token>`. Never place the raw token in URLs, browser
JavaScript, Docker images, committed `.env` files, or diagnostic output.

Principal IDs and key IDs are stable, non-secret audit identifiers. Roles are
carried in the authenticated principal for Phase C1.3 authorization; this phase
does not yet enforce role-specific access.

## Rotation

1. Generate a new independent token and digest.
2. Add a second credential with a new `key_id` under the same principal.
3. Deploy the API configuration so both credentials overlap.
4. Update the server-side caller secret and verify authenticated requests.
5. Disable the old credential, deploy, and then remove it after the rollback
   window.

Disabled and expired credentials always receive the same `401` response as an
unknown token. Verification hashes the submitted token once and compares every
configured fixed-length digest with `hmac.compare_digest`.

## Health checks and deployment boundaries

Docker Compose currently uses PostgreSQL and Redis health checks for startup and
does not call the API readiness route. An orchestrator readiness probe must send
a dedicated internal principal's bearer token to `/health/ready`; liveness probes
should use public `/health/live` and need no secret.

The legacy `automotive.api` module is an unauthenticated benchmark compatibility
application. It is not the authoritative runtime and must not be used as a
shared or production Uvicorn entry point. Deploy only
`automotive_quality.api.main:app`.
