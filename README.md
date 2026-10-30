# Automotive Work Order Data Quality & AI-Assisted Test Engineering Platform

**Release:** [`v2.0.0 — Measured AI Quality Platform`](docs/releases/v2.0.0.md)

> AI improved coverage over the deterministic baseline and reduced human effort, but it did not outperform human-only coverage and introduced unsupported assumptions. RCA reduced investigation time but failed accuracy thresholds. Both AI quality policies therefore correctly `BLOCK` the current configuration.

**Live recruiter overview:** [English](https://automotive-ai-quality-engineering.dearmole20.chatgpt.site/en) · [中文](https://automotive-ai-quality-engineering.dearmole20.chatgpt.site/zh) · [Source repository](https://github.com/lichangqing1/automotive-work-order-intelligence)

The bilingual, evidence-first landing page is implemented under [`landing/`](landing/README.md). English is the default, with stable `/en` and `/zh` routes sharing the same generated metrics and evidence. The Streamlit dashboard remains the separate engineering console.

A production-shaped quality engineering platform for automotive after-sales, OTA, and diagnostic work orders.

> Ingest relational work-order data → validate and quarantine defects → reconcile source, curated, SQL mart, and API outputs → manage test executions → retrieve historical evidence → assist resolution and RCA → enforce policy-driven quality gates.

## Why this project exists

Automotive work-order operations become unreliable when identifiers are missing, state transitions are inconsistent, OTA versions are incompatible, repeated faults are not connected, or analytics disagree with source systems. This project treats those problems as an integrated **data testing and test engineering system**, with AI added only behind deterministic controls.

It demonstrates four connected capabilities:

1. **Data engineering and data testing** — relational sources, Python processing, SQL validation, reconciliation, and business marts.
2. **Test development** — versioned quality assets, explicit test-run/result models, evidence, severity, and API contracts.
3. **AI for testing** — provider-neutral structured requirement analysis, test generation, DQ-rule drafting, and evidence-gated RCA.
4. **AI quality engineering** — executable benchmarks and generic metric policies that block regressions.

## Implemented architecture

```text
Streamlit developer UI / FastAPI /api/v1
                    │
          Application and domain services
        ┌───────────┼───────────────┐
        ▼           ▼               ▼
 Work orders   Data quality    Test management
 Reconciliation Rule lifecycle Run / result evidence
        │           │               │
        └───────────┼───────────────┘
                    ▼
        SQLAlchemy 2 + Alembic migrations
                    ▼
              PostgreSQL 16

Deterministic baseline: TF-IDF retrieval + evidence-grounded assistance
Cross-cutting: Pydantic settings, structured schemas, quality policies, CI
```

The repository is a modular monolith. PostgreSQL + `automotive_quality` + `/api/v1` is the single authoritative runtime. API handlers remain thin; the original `automotive` package contains compatibility shims for explicitly labelled, non-production benchmarks only. Production retrieval and the dashboard never read SQLite, generated CSVs, or fallback data.

## Current capabilities

| Area | Capability |
|---|---|
| Platform schema | Vehicles, OTA releases, service centers, work orders, immutable version snapshots, diagnostics, resolution history, versioned DQ results, test assets/runs, AI audit runs, evaluation runs/metrics |
| Database lifecycle | PostgreSQL-first SQLAlchemy models and Alembic migration; full schema can be recreated from zero |
| Data quality | Unique, null, allowed-value, comparison, conditional, foreign-key, range, regex, aggregate reconciliation, and freshness rules |
| Governance | DQ lifecycle: `DRAFT → REVIEWED → APPROVED → ACTIVE → DEPRECATED` |
| Reconciliation | Raw − quarantined = clean; grouped SQL/mart/API comparisons with evidence and variance |
| SQL | Referential-integrity, OTA-compatibility, source-target checks, and PostgreSQL business marts |
| Runtime | PostgreSQL-backed ingestion → enterprise DQ → persistent runs/results → reconciliation → database KPI API |
| Test management | Persistent typed test cases, runs, expected/actual values, affected rows, evidence, and status summaries |
| AI for testing | Mock/OpenAI provider abstraction, operational prompt registry and hashes, canonical DQ DSL, review-required generated assets, evidence validation, AI-run audit |
| API | Structured requirement analysis, test generation, DQ rule generation, RCA, explicit deterministic baselines, retrieval, persisted test history/KPIs, health checks |
| Quality gates | Generic dotted-metric/operator/threshold policy engine configured in YAML |
| Delivery | Dockerfile, PostgreSQL/Redis/API Compose stack, lint/migration/test/container CI |

## Quick start with Docker

```bash
cp .env.example .env
docker compose up --build
```

Then open:

- API documentation: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/health/live`
- Readiness: `http://localhost:8000/health/ready`

## Native development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
docker compose up -d postgres redis
alembic upgrade head
alembic current
alembic check
pytest -q
ruff check src tests
```

Run the PostgreSQL-backed enterprise path:

```bash
python scripts/run_enterprise_platform.py --rows 30000 --dataset-version local-v1
```

Run the explicitly non-production comparison benchmark and executable AI evaluation:

```bash
python scripts/baselines/build_legacy_baseline.py --rows 30000
python scripts/run_ai_evaluation.py
```

Run the interfaces:

```bash
uvicorn automotive_quality.api.main:app --reload
streamlit run dashboard/app.py
```

## API examples

```bash
curl -X POST 'http://localhost:8000/api/v1/retrieval/search?top_k=5' \
  -H 'Content-Type: application/json' \
  -d '{
    "vehicle_model": "Model-X",
    "ota_version": "6.2.1",
    "description": "central display intermittently black after OTA",
    "error_code": "IVI_E104"
  }'
```

Important endpoints:

```text
GET  /health/live
GET  /health/ready
POST /api/v1/retrieval/search
GET  /api/v1/datasets
GET  /api/v1/datasets/{version}
POST /api/v1/ai/requirements/analyze
POST /api/v1/ai/tests/generate
POST /api/v1/ai/dq-rules/generate
POST /api/v1/ai/rca/analyze
POST /api/v1/requirements/import/jira
POST /api/v1/requirements/{id}/analyze
POST /api/v1/requirements/{id}/generate-tests
GET  /api/v1/reviews/{id}
POST /api/v1/reviews/{id}/sync
POST /api/v1/reviews/{id}/decision  # local tracker only
POST /api/v1/reviews/{id}/start
POST /api/v1/reviews/{id}/assessment
POST /api/v1/test-runs
GET  /api/v1/traceability/requirements/{id}
POST /api/v1/external-sync/{link_id}/retry
POST /api/v1/baselines/ai/resolution
POST /api/v1/baselines/ai/rca
GET  /api/v1/test-runs
GET  /api/v1/test-runs/{run_id}
GET  /api/v1/metrics/overview
GET  /api/v1/ai-value/experiments
```

## Quality policy example

```yaml
- metric: retrieval.hit_rate_at_5
  operator: ">="
  threshold: 0.70
- metric: rag.unsupported_claim_rate
  operator: "<="
  threshold: 0.0
```

The evaluator is metric-agnostic. Adding a metric does not require changing Python gate logic.

## AI-assisted testing and Jira review

The platform persists imported Jira requirements as immutable versions, links each AI analysis and generated test version to its `AIRun`, and creates one review issue per generation batch. Generated tests remain `REVIEW_REQUIRED` until the tracker reports an approved state; rejected or pending versions cannot execute. Every `TestResult` has relational links to the exact `TestCaseVersion`, external defect link, and RCA `AIRun`. Deterministic results commit before Jira synchronization; external work records `PENDING`, `SUCCEEDED`, or `FAILED` with retry state, and retry-safe external IDs prevent duplicate Jira issues.

CI uses `ISSUE_TRACKER=local`. Set `ISSUE_TRACKER=jira` plus `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, and `JIRA_PROJECT_KEY` for Jira Cloud. Credentials are never stored in the repository. The opt-in live contract is run with `pytest -m jira_integration tests/integration/test_jira_live.py`; normal CI never contacts Jira.

## Task 3: measured AI value

The controlled benchmark compares the same curated requirement or failure evidence across a deterministic baseline and an AI-assisted variant. It measures scenario, boundary, negative, integration, and data-quality coverage; duplicate, executable, approval, edit, rejection, and unsupported-assumption rates; human effort and elapsed time; and RCA accuracy, evidence support, unsupported claims, abstention, usefulness, and investigation time.

Mock runs are regression-only and are always marked `NOT PUBLISHABLE`. A test-generation result becomes publishable only when an immutable real-provider run is rescored with exactly one human review for every baseline and AI-generated test, plus one matched human-only timing record for every requirement. RCA likewise requires exactly one review per case and run. Missing, duplicate, or unexpected records block publication. The runner never overwrites previous experiments and retains configuration, dataset hash, raw outputs, review queue, statistical summaries, and policy results.

```bash
python scripts/run_ai_value_experiment.py \
  --experiment test-generation \
  --dataset evaluation/ai_value/requirements.jsonl \
  --provider openai \
  --model "$LLM_MODEL" \
  --runs 3

# Complete the generated review_queue.jsonl, then score those exact outputs:
python scripts/run_ai_value_experiment.py \
  --score-run results/ai_value/EXP-... \
  --reviews evaluation/ai_value/reviews.jsonl \
  --human-baseline evaluation/ai_value/human_only_measurements.jsonl \
  --database-url "$DATABASE_URL"

python scripts/run_ai_value_experiment.py \
  --experiment rca \
  --dataset evaluation/ai_value/rca_cases.jsonl \
  --provider openai \
  --model "$LLM_MODEL" \
  --runs 3

python scripts/run_ai_value_experiment.py \
  --score-run results/ai_value/EXP-... \
  --reviews evaluation/ai_value/rca_reviews.jsonl \
  --database-url "$DATABASE_URL"
```

See `evaluation/ai_value/README.md` and `docs/AI_VALUE_EVALUATION.md`. Do not quote an improvement percentage until the real-provider output has completed human review and the generated report says `publishable: true`.

### Measured AI-value evidence

The completed `ai-value-v1` test-generation and RCA experiments both used OpenAI with three runs, complete human review, and immutable rescoring; both reports are marked `publishable: true`. The sanitized evidence and reproducibility manifest are in [`artifacts/ai_value/`](artifacts/ai_value/README.md).

Test generation increased mean requirement coverage from 5.83% to 49.35% and mean negative coverage from 20.00% to 47.96%. Measured human-effort saving was 48.98%, and end-to-end saving was 19.00%. However, the AI unsupported-assumption rate was 100%, and the proposed test-generation policy returned `BLOCK`.

RCA reduced mean active investigation time from 77.60 seconds to 49.41 seconds, and recommended-check usefulness averaged 75.56%. Evidence support was 94.52%, but unsupported claims were 5.48%, correct abstention was 13.33%, and root-cause accuracy was 0%. The proposed RCA policy also returned `BLOCK`.

These results support metric-specific gains and regressions only. They do not establish universal AI superiority, and the policy thresholds remain `proposed_until_calibrated`.

## Repository map

```text
src/automotive_quality/
  api/                    Versioned platform API
  domains/
    data_quality/         Rules, lifecycle, execution
    evaluation/           Generic quality policies
    ai/                   Providers, structured workflows, evals
    testing/              Test assets and execution runs
    work_orders/          Reconciliation services
  infrastructure/database/ SQLAlchemy models and sessions
  shared/                 Settings and structured logging
src/automotive/           Working deterministic compatibility baseline
migrations/               Alembic environment and initial schema
sql/                      Relational validations and marts
evaluation/               Fast regression and controlled AI-value benchmark inputs
prompts/                  Versioned prompt policies
configs/                  Rules, policies, and model configuration
tests/                    Unit, integration, API, DQ, retrieval, and regression tests
docs/adr/                 Architecture decisions
docs/runbooks/            Operational procedures
```

## Measured baseline

The committed reports are generated by executable code, not manually entered dashboard constants. Rebuild before quoting results. Retrieval evaluation distinguishes true Recall@K and Precision@K from Hit Rate@K and MRR. The controlled 30,000-row enterprise DQ benchmark now deterministically records 1,200 TP, 0 FP, and 0 FN.

## Deliberate scope boundary

The persistent runtime, provider-neutral AI-for-testing layer, and versioned AI-value evaluation program are implemented. CI continues to use `MockProvider`, while completed OpenAI experiments with full human review are published as sanitized aggregate evidence under `artifacts/ai_value/`. Both current AI-value policies return `BLOCK`, preserving measured regressions rather than presenting the model as production-approved. The committed `ai-value-v1` benchmark has 30 requirement and 30 RCA cases. Celery workers, semantic/pgvector retrieval, and a React console remain subsequent stages. Redis is present for the planned worker but is not represented as active task execution.

See [architecture](docs/AUTOMOTIVE_ARCHITECTURE.md), [local runbook](docs/runbooks/local-development.md), and the ADRs for decisions and tradeoffs.
