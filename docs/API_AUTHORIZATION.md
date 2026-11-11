# API authorization and actor accountability

Authentication establishes a principal; authorization separately maps that
principal's configured roles to explicit permissions. Unknown roles grant no
permissions. Roles do not inherit from one another.

| Role | Explicit permissions |
| --- | --- |
| `reader` | Read platform data and governed evidence |
| `operator` | Read; invoke AI; import/analyze requirements; generate tests; submit test results; retry failed external synchronization |
| `reviewer` | Read; start, assess, synchronize, approve, or reject reviews |
| `administrator` | Every currently defined permission, including the explicit self-review exception |

Missing or invalid authentication returns HTTP 401. An authenticated principal
without the required permission receives HTTP 403 before database, AI, or Jira
business dependencies execute.

## Endpoint permission matrix

| Operations | Required role |
| --- | --- |
| `POST /api/v1/retrieval/search` | reader, operator, reviewer, administrator |
| `GET /api/v1/metrics/overview` | reader, operator, reviewer, administrator |
| `GET /api/v1/datasets` and `GET /api/v1/datasets/{version}` | reader, operator, reviewer, administrator |
| `GET /api/v1/test-runs` and `GET /api/v1/test-runs/{run_id}` | reader, operator, reviewer, administrator |
| `GET /api/v1/reviews/{review_id}` | reader, operator, reviewer, administrator |
| `GET /api/v1/traceability/requirements/{id}` | reader, operator, reviewer, administrator |
| `GET /api/v1/ai-value/experiments` | reader, operator, reviewer, administrator |
| `POST /api/v1/baselines/ai/resolution` | operator, administrator |
| `POST /api/v1/baselines/ai/rca` | operator, administrator |
| `POST /api/v1/baselines/dq/rules/draft` | operator, administrator |
| `POST /api/v1/ai/requirements/analyze` | operator, administrator |
| `POST /api/v1/ai/tests/generate` | operator, administrator |
| `POST /api/v1/ai/dq-rules/generate` | operator, administrator |
| `POST /api/v1/ai/rca/analyze` | operator, administrator |
| `POST /api/v1/requirements/import/jira` | operator, administrator |
| `POST /api/v1/requirements/{id}/analyze` | operator, administrator |
| `POST /api/v1/requirements/{id}/generate-tests` | operator, administrator |
| `POST /api/v1/test-runs` | operator, administrator |
| `POST /api/v1/external-sync/{link_id}/retry` | operator, administrator |
| `POST /api/v1/reviews/{review_id}/sync` | reviewer, administrator |
| `POST /api/v1/reviews/{review_id}/start` | reviewer, administrator |
| `POST /api/v1/reviews/{review_id}/assessment` | reviewer, administrator |
| `POST /api/v1/reviews/{review_id}/decision` | reviewer, administrator |

`/health/live` remains public. `/health/ready` requires authentication but is
not a business operation and does not use role authorization.

## Actor binding and resource integrity

New API-originated records persist the authenticated principal ID for requirement
imports, generated test-case versions, test-run submissions, result evidence,
review activity, and external-sync retries. Client-supplied reviewer text cannot
override the authenticated principal.

Review artifacts must exist and belong to one requirement version. A principal
cannot review test cases it generated. Administrators have an explicit exception
for recovery operations. Historical review batches without generation actor
metadata require an administrator; existing decisions and history are not
rewritten.

Test execution continues to validate requirement/test-case/dataset relationships.
External-sync retries now validate that the link points to a supported, existing
review or test-result record before invoking Jira.

The platform has no tenant or resource-owner model. Consequently, authorization
does not invent tenant isolation: any role with the read permission can read the
current platform's resources. Tenant-scoped ownership requires a separate data
model and security design.
