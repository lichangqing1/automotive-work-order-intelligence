# Portfolio architecture

These diagrams show implemented components only. The bilingual landing site is a read-only presentation surface, not part of the authoritative engineering runtime. Celery workers and pgvector are intentionally absent because they are not implemented.

## A. Platform architecture

```mermaid
flowchart TB
  subgraph Presentation["Presentation boundaries"]
    Landing["Bilingual recruiter landing\nread-only generated evidence"]
    Console["Streamlit engineering console\nAPI client only"]
  end

  subgraph API["Operational API boundary"]
    FastAPI["FastAPI /api/v1"]
    Security["Bearer authentication · RBAC\nrequest limits · schema validation"]
    Redis["Redis 7\nquotas · rate limits · AI leases"]
  end

  subgraph Services["Domain and application services"]
    DQ["Data-quality rules\nquarantine · reconciliation"]
    Testing["Test management\nversions · runs · evidence"]
    Review["Review workflows\nactor attribution · traceability"]
    AIService["AI workflow service\nstructured contracts · validation"]
    Baseline["Deterministic baselines\nand AI evaluation policies"]
  end

  subgraph Persistence["Authoritative persistence"]
    ORM["SQLAlchemy 2 · Alembic"]
    PG["PostgreSQL 16\ndatasets · DQ · tests · reviews"]
    Audit["AI Run audit · durable AI operations\ningestion and sync audit"]
  end

  subgraph External["Adapter boundary"]
    Providers["LLMProvider\nMockProvider · optional OpenAIProvider"]
    Trackers["IssueTracker\nLocalIssueTracker · optional Jira"]
  end

  Landing -. "generated metrics" .-> PG
  Console --> FastAPI
  FastAPI --> Security --> Redis
  Redis --> DQ
  Redis --> Testing
  Redis --> Review
  Redis --> AIService
  DQ --> ORM
  Testing --> ORM
  Review --> ORM
  AIService --> ORM
  Baseline --> ORM
  ORM --> PG
  ORM --> Audit
  AIService --> Providers
  Review --> Trackers
```

Solid arrows represent operational calls or persistence. The dotted landing arrow represents exported, read-only evidence; the landing site does not query the runtime database. Jira and OpenAI are optional adapters. CI and the safe demo use local/mock implementations.

## B. Protected AI operation lifecycle

```mermaid
flowchart TD
  Request["Authenticated API request\nIdempotency-Key + payload"] --> Auth{"Authentication valid?"}
  Auth -- "no" --> R401["401 · no business action"]
  Auth -- "yes" --> RBAC{"Authorized for resource?"}
  RBAC -- "no" --> R403["403 · no quota or business action"]
  RBAC -- "yes" --> Admission{"Redis quota and lease admitted?"}
  Admission -- "no" --> R429["429 or sanitized 503"]
  Admission -- "yes" --> Claim["PostgreSQL durable operation claim\nprincipal + type + target + key + request hash"]

  Claim --> Existing{"Existing scoped identity?"}
  Existing -- "different payload" --> RConflict["409 IDEMPOTENCY_KEY_CONFLICT"]
  Existing -- "RUNNING" --> RRunning["409 OPERATION_IN_PROGRESS"]
  Existing -- "AMBIGUOUS or FAILED" --> RBlocked["409 · no automatic execution"]
  Existing -- "SUCCEEDED" --> Replay["Replay stored response\nIdempotent-Replay: true"]
  Existing -- "new" --> Provider["Provider execution"]

  Provider --> Lease{"Lease still owned?"}
  Lease -- "lost or timeout" --> Ambiguous["Persist AMBIGUOUS\nreturn sanitized 503 + operation ID"]
  Lease -- "yes" --> Validate["Structured output and evidence validation"]
  Validate --> Persist["Business persistence\nAI Run · generated assets"]
  Persist --> Governed["Review / optional Jira sync\nstable external identity"]
  Governed --> Complete["Owner-token terminal update\nSUCCEEDED + stored response"]
  Complete --> Response["Response + X-AI-Operation-ID"]

  Status["GET /api/v1/ai-operations/{id}\nauthenticated owner-scoped lookup"] --> Claim
  Ambiguous -. "manual reconciliation" .-> Status

  RedisNote["Redis lease and PostgreSQL transaction\nare not one atomic distributed transaction"]
  RedisNote -.-> Lease
```

The lifecycle prevents automatic duplicate execution under the tested retry and concurrency conditions. It does not guarantee exactly-once external-provider execution or billing across arbitrary process/network failure.
