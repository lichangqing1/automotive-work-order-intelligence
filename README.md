# Automotive Work Order Data Quality & AI-Assisted Test Engineering Platform

English | [简体中文](README.zh-CN.md)

An evidence-first portfolio project that combines automotive work-order data quality, test development, governed AI assistance, human review, and measurable release gates in one traceable PostgreSQL-backed platform.

**Explore:** [live bilingual recruiter site](https://automotive-ai-quality-engineering.p154820.chatgpt.site/en) · [portfolio evidence map](docs/portfolio/README.md) · [architecture](docs/portfolio/ARCHITECTURE.md) · [reproducible demo](docs/portfolio/DEMO_GUIDE.md) · [source repository](https://github.com/lichangqing1/automotive-work-order-intelligence)

## Verified engineering highlights

- A controlled **30,000-record synthetic** work-order benchmark injected 1,200 known defects and detected 1,200/1,200 within that declared benchmark. This is not a production-accuracy claim.
- Versioned DQ rules, quarantine, source-to-target reconciliation, SQL marts, API contracts, test evidence, and immutable dataset identities share one authoritative PostgreSQL runtime.
- AI-generated tests remain `REVIEW_REQUIRED`; pending or rejected versions cannot execute. Submitted test results are validated evidence, not automatically executed test steps.
- Provider-backed operations use authenticated identities, RBAC, Redis quotas/leases, durable PostgreSQL operation claims, response replay, and `AMBIGUOUS` recovery.
- [GitHub Actions run 43178347023](https://github.com/lichangqing1/automotive-work-order-intelligence/actions/runs/43178347023) passed at commit `719a0bc`: PostgreSQL 12 passed with zero skips, Redis 4 passed with zero skips, and the full suite reported 246 passed and 1 intentional live-Jira skip.
- Both historical AI quality policies remain **BLOCK**. Controlled synthetic staging is **CONDITIONAL GO**; shared and production deployment remain **NO-GO** pending operational controls.

## Architecture overview

The project is a modular monolith. FastAPI `/api/v1`, domain/application services, SQLAlchemy/Alembic, and PostgreSQL form the authoritative engineering runtime. Streamlit is an API-only engineering console. The bilingual landing site is a separate, read-only portfolio presentation.

```text
Landing site (read-only evidence)      Streamlit engineering console
                                                  │
                                                  ▼
                                      FastAPI /api/v1
                           auth → RBAC → limits → Redis admission
                                                  │
                             domain and application services
                       DQ · reconciliation · tests · reviews · AI
                           │                         │
                           ▼                         ▼
                 PostgreSQL + audits      Mock/OpenAI provider
                                           Local/Jira tracker
```

See the [implemented architecture and protected AI lifecycle diagrams](docs/portfolio/ARCHITECTURE.md). The diagrams deliberately exclude unimplemented Celery workers and pgvector retrieval.

## Core capabilities

| Area | Implemented capability |
|---|---|
| Data quality | Completeness, uniqueness, validity, comparison, conditional, foreign-key, range, regex, freshness, and aggregate reconciliation rules |
| Data lifecycle | Immutable dataset versions, content fingerprints, repeat-safe ingestion, quarantine, and durable attempt auditing |
| Reconciliation | Raw − quarantined = clean plus grouped source, SQL mart, and API variance evidence |
| Test engineering | Versioned cases, approvals, runs, expected/actual results, dataset identity, evidence, defects, and requirement traceability |
| AI assistance | Provider-neutral structured requirement analysis, test generation, DQ-rule drafts, RCA, prompt hashes, and AI-run auditing |
| AI governance | Review-required assets, exact evidence-ID checks, human review completeness, deterministic policies, and preserved BLOCK decisions |
| API security | Bearer authentication, RBAC, actor attribution, 1 MiB body limit, constrained schemas, Jira DLP, sanitized errors, and security events |
| Distributed protection | Redis rate limits and concurrency leases plus durable AI-operation idempotency and reconciliation status |
| Delivery | Alembic migrations, Docker, PostgreSQL/Redis integration gates, Ruff, pytest, pip-audit, and bilingual landing build |

Redis actively enforces rate limits and provider concurrency. It is **not** presented as a background task-worker system; Celery-style workers remain outside the implemented scope.

## Engineering case studies

1. [Data quality: controlled defects, quarantine, and reconciliation](docs/portfolio/CASE_DATA_QUALITY.md)
2. [RCA metric integrity: why 94.52% became 13.33%](docs/portfolio/CASE_RCA_METRIC_INTEGRITY.md)
3. [AI retry safety: durable claims after ambiguous 503 responses](docs/portfolio/CASE_AI_RETRY_SAFETY.md)

Each case links the problem, reproduction, root cause, implementation, tests, before/after evidence, and remaining limitations.

## Corrected AI evaluation interpretation

The preserved `ai-value-v1` RCA report originally recorded 94.52% evidence support and 5.48% unsupported claims. A later metric-integrity review found that v1 conflated citation correctness with actual claim support and gave overly favorable treatment to omitted or incorrectly identified claims.

| RCA metric | Preserved historical v1 | Corrected `rca-metrics-v2` | Current interpretation |
|---|---:|---:|---|
| Evidence support | 94.52% | **13.33%** | v1 overstated support |
| Unsupported claims | 5.48% | **76.67%** | unacceptable claim risk |
| Root-cause accuracy | 0% | **0%** | autonomous diagnosis blocked |
| Quality policy | BLOCK | **BLOCK** | decision unchanged |

The current portfolio uses the corrected v2 values from the [comparison report](docs/reports/RCA_METRIC_INTEGRITY_V2_COMPARISON.md) and [versioned derived record](docs/portfolio/data/rca_metrics_v2.json). The historical JSON, human reviews, datasets, thresholds, and manifest remain unchanged for provenance.

Test generation showed metric-specific gains—49.35% AI-assisted requirement coverage versus 5.83% for the deterministic template baseline and 48.98% measured human-effort saving—but did not beat 63.78% human-only coverage and recorded a 100% unsupported-assumption rate. Its policy also remains `BLOCK`.

## Reproducible demo

The [demonstration guide](docs/portfolio/DEMO_GUIDE.md) uses synthetic fixtures, `MockProvider`, `LocalIssueTracker`, and isolated test infrastructure. It requires no paid provider, live Jira, customer data, database reset, or Redis flush.

Validation-only preview:

```bash
source .venv/bin/activate
pytest -q tests/test_automotive_generator_quality.py
pytest -q tests/test_api_authentication.py tests/test_api_authorization.py
pytest -q tests/test_ai_operation_idempotency.py tests/test_rca_metric_integrity.py
python scripts/export_landing_data.py
pytest -q tests/test_landing_data.py
```

These commands validate deterministic detection, security denials, idempotency contracts, corrected RCA scoring, and landing provenance. They do not claim to execute manual test steps automatically.

## Security, retry, and release gates

All `/api/v1` operations require bearer authentication except minimal liveness. Authorization, Redis admission, request validation, and business dependencies are independently enforced. Shared/staging/production provider calls require an 8–128 character `Idempotency-Key`.

```text
GET /api/v1/ai-operations/{operation_id}
```

The authenticated status endpoint exposes a caller's operation state for safe reconciliation. `SUCCEEDED` requests replay their stored response; payload conflicts, in-progress work, and ambiguous outcomes return controlled conflicts. `RUNNING` and `AMBIGUOUS` operations are never automatically re-executed. Exactly-once external-provider execution or billing across arbitrary crashes is not guaranteed.

Read [authentication](docs/API_AUTHENTICATION.md), [authorization](docs/API_AUTHORIZATION.md), [rate limiting](docs/API_RATE_LIMITING.md), [security hardening](docs/API_SECURITY_HARDENING.md), [operation idempotency](docs/AI_OPERATION_IDEMPOTENCY.md), and the [release gate](docs/reports/C1_SECURITY_RELEASE_GATE.md).

## Technology

Python 3.12 · FastAPI · Pydantic · PostgreSQL 16 · SQLAlchemy 2 · Alembic · Redis 7 · pytest · Ruff · OpenAI structured outputs · Jira REST · Streamlit · Docker · GitHub Actions · React/Vinext landing site

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,security]'
docker compose up -d postgres redis
alembic upgrade head
pytest -q
ruff check .
```

Local Docker Compose publishes development ports and uses placeholder credentials. It is not a production deployment specification. Configure digest-only API principals before calling protected routes; see the [local runbook](docs/runbooks/local-development.md).

Important API operations include:

```text
GET  /health/live
GET  /health/ready
POST /api/v1/ai/requirements/analyze
POST /api/v1/ai/tests/generate
POST /api/v1/ai/dq-rules/generate
POST /api/v1/ai/rca/analyze
POST /api/v1/requirements/{id}/analyze
POST /api/v1/requirements/{id}/generate-tests
GET  /api/v1/ai-operations/{operation_id}
POST /api/v1/test-runs
GET  /api/v1/traceability/requirements/{id}
GET  /api/v1/metrics/overview
GET  /api/v1/ai-value/experiments
```

## Evidence and documentation

- [Portfolio evidence navigation](docs/portfolio/README.md)
- [AI evaluation protocol](docs/AI_VALUE_EVALUATION.md)
- [Preserved aggregate artifacts](artifacts/ai_value/README.md)
- [Corrected RCA comparison](docs/reports/RCA_METRIC_INTEGRITY_V2_COMPARISON.md)
- [C1 security release gate](docs/reports/C1_SECURITY_RELEASE_GATE.md)
- [Architecture decisions](docs/adr/ADR-001-modular-monolith.md)
- [v2.0.0 evidence release](docs/releases/v2.0.0.md)

## Limitations and readiness

- All benchmark data is synthetic or curated; no claim generalizes to unobserved production data.
- Prompt injection is reduced by trust boundaries and schema validation, not eliminated.
- Provider execution and billing cannot be made absolutely exactly-once without provider-native support.
- Semantic/pgvector retrieval, Celery workers, and a dedicated React engineering console are not implemented.
- Production Redis HA/TLS, application TLS termination, secret-manager delivery, network isolation, backup recovery, and security-event operations remain unverified.
- Local development and isolated engineering verification are `GO`; controlled synthetic staging is `CONDITIONAL GO`; shared and production deployment remain `NO-GO`.

The project demonstrates how to measure both AI value and AI failure honestly—and how to block promotion when evidence is incomplete or quality is insufficient.
