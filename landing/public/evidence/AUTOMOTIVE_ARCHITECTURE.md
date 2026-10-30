# Automotive Work Order Data Quality & AI-Assisted Test Engineering Platform

## Domain boundary

The system covers after-sales service, OTA/software incidents, and diagnostic escalations. It does not attempt warranty adjudication, live vehicle control, or safety-critical autonomous decisions.

## Core entities

- `vehicles`: model, production year, hardware, software, OTA version, and region.
- `work_orders`: operational state, category, priority, description, ownership, SLA, and resolution.
- `ota_releases`: release dates, notes, and known issues.
- `diagnostic_events`: work-order-linked error-code evidence.
- curated marts: daily operations, OTA quality, vehicle/model issues, and team performance.
- `datasets`, `dataset_versions`, and `ingestion_runs`: source-independent ingestion and lineage.
- `dq_rules`, `dq_rule_versions`, `dq_runs`, and `dq_results`: managed quality assets and execution evidence.
- `test_cases`, `test_runs`, and `test_results`: product-level test management.
- `ai_runs`, `evaluation_runs`, and `evaluation_metrics`: AI traceability and benchmark history.

## Module boundaries

```text
automotive_quality/
├── domains/          Business rules with no FastAPI dependency
├── infrastructure/   SQLAlchemy and external adapters
├── api/              Versioned transport contracts
└── shared/           Settings and structured logging
```

The design is a modular monolith. PostgreSQL, `automotive_quality`, and `/api/v1` form the only production runtime. The older `automotive` package contains compatibility shims for explicitly labelled comparison benchmarks and is never imported by production modules.

## Persistence and migrations

PostgreSQL 16 is the primary platform store. SQLAlchemy models define operational, quality, testing, AI-audit, and evaluation tables. The squashed `20261015_0001` Alembic baseline uses explicit table, constraint, foreign-key, and index operations and never imports evolving application metadata. CI upgrades a brand-new PostgreSQL database to head and runs `alembic check` to detect schema drift. SQLite is used only for fast isolated schema and repository tests.

The synthetic generator is an infrastructure source adapter, not the platform itself. `ingest_generated_dataset` records dataset/version/run metadata and writes through the same relational boundary that a future external adapter would use.

## Trust boundaries

Deterministic Python and SQL discover and aggregate evidence. The assistance layer may interpret only the retrieved evidence. It cannot update source work orders or approve generated quality rules.

`LLMProvider` isolates business workflows from vendors. CI uses `MockProvider`; `OpenAIProvider` uses Responses API Structured Outputs and can be enabled through settings. `PromptRegistry` loads versioned YAML, and every AI run records its prompt version and content hash. Both paths share Pydantic schemas, the canonical DQ rule DSL, review-required asset states, explicit insufficient-evidence behavior, AI-run audit records, and deterministic execution gates. Older deterministic assistants are exposed only below `/api/v1/baselines`.

Each ingestion calculates component hashes for all four relational inputs and a combined manifest hash. Immutable `work_order_snapshots` retain exact version payloads while `work_orders` serves the current operational projection. DQ results reference the exact immutable rule version that produced them.

## Data-quality flow

1. Raw records are immutable build inputs.
2. YAML rules are parsed into typed Pydantic models.
3. Every rule produces checked count, failed count, pass rate, severity, and status.
4. Rows failing configured checks are quarantined before the clean layer.
5. Critical failures set the quality gate to failed; metrics are still persisted for investigation.
6. Rule assets follow `DRAFT → REVIEWED → APPROVED → ACTIVE → DEPRECATED`.

Supported execution types include completeness, uniqueness, allowed values, comparisons, conditional requirements, ranges, regular expressions, foreign keys, freshness, and aggregate reconciliation.

## Python and SQL responsibilities

- Python owns ingestion orchestration, normalization, feature engineering, rule execution, and workflow state.
- SQL owns relational joins, referential-integrity checks, OTA compatibility, reconciliation queries, and business marts.
- Automated reconciliation verifies raw − quarantined = clean and compares grouped mart/API values with exact variance evidence.

Intentional defects include missing vehicle IDs, invalid states, invalid priorities, impossible resolution timestamps, and duplicate IDs. Because defects are traceable by row, detection performance is measured rather than asserted informally.

## Retrieval and RAG evaluation

Production retrieval requires an explicit `DatasetVersion`, loads resolved cases from immutable PostgreSQL `WorkOrderSnapshot` records, and returns `503 RETRIEVAL_INDEX_NOT_READY` rather than manufacturing fallback data. The API depends on a retrieval protocol; TF-IDF is retained as the explicitly labelled lexical baseline. Evaluation reports true Recall@K and Precision@K separately from Hit Rate@K and MRR.

The Streamlit interface is an API client only. It has no database driver, filesystem dataset, or independent metric calculations, so FastAPI remains the sole presentation contract.

For production use, replace the benchmark with manually curated query/relevant-case judgments and add semantic embeddings. Generic policies in `configs/quality_policies.yaml` define metric paths, comparison operators, and thresholds without domain-specific gate code.

## API contracts and health

Platform endpoints are rooted at `/api/v1`. Liveness confirms that the process is serving requests. Readiness executes `SELECT 1` against the configured PostgreSQL dependency and returns HTTP 503 when unavailable.

Test runs are first-class objects with explicit status, expected/actual values, affected rows, evidence, and timing. PostgreSQL repositories persist test, DQ, evaluation, and AI audit history so API restarts do not erase platform state.

## Human-reviewed AI testing workflow

Jira is an adapter behind the generic `IssueTracker` protocol, not a system of record or execution engine. `RequirementVersion`, `TestCaseVersion`, `ReviewRequest`, `TestResult`, and `ExternalIssueLink` preserve the requirement → generation AI run → draft → review → execution → defect → RCA AI run chain with relational keys in PostgreSQL. Traceability queries scope every review, result, run, issue, and RCA record to the selected requirement. Deterministic results commit before external calls; Jira synchronization is a retryable `PENDING/SUCCEEDED/FAILED` process. The Jira adapter uses stable labels derived from internal idempotency keys to recover safely from ambiguous network responses.

## Security and responsible use

- Synthetic data contains no customer PII.
- Rule generation produces inert, review-required structures.
- No generated diagnosis is written back to a service system.
- Low-evidence queries return a refusal-style response.
- API inputs are typed and constrained.
- Operational users remain responsible for diagnosis and repair approval.

## Explicit next stages

The following are not represented as finished: Celery job execution, semantic/pgvector retrieval, a broad adversarial AI benchmark, and the React console. They follow only after the new PostgreSQL runtime and structured AI workflows remain stable.
