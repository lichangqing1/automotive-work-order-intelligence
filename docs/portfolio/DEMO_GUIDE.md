# Safe reproducible demonstration

This demonstration is validation-only by default. It uses synthetic data, `MockProvider`, `LocalIssueTracker`, isolated pytest databases, and optional dedicated PostgreSQL/Redis test services. It never contacts live Jira or a paid model, resets an existing database, flushes Redis, or rewrites historical AI artifacts.

## Preconditions

```bash
cd /path/to/automotive-work-order-intelligence
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,security]'
```

If the environment is already installed, use the existing `.venv`. Do not copy `.env.example` over an existing `.env` and do not display configured credentials.

## 1. Controlled data-quality detection

Command:

```bash
pytest -q tests/test_automotive_generator_quality.py tests/test_reconciliation_policy.py
```

Expected: the tests pass and confirm the deterministic injected-row oracle plus reconciliation policy. Evidence: [data-quality case study](CASE_DATA_QUALITY.md). Cleanup: none; pytest uses synthetic in-memory fixtures.

Safety boundary: 1,200/1,200 applies only to the controlled 30,000-row synthetic benchmark.

## 2. Authentication and authorization denials

Command:

```bash
pytest -q tests/test_api_authentication.py tests/test_api_authorization.py
```

Expected: missing credentials produce 401, insufficient permission produces 403, self-review is denied, and rejected operations do not call business or tracker actions. Cleanup: none; tests use disposable databases and synthetic principals.

## 3. AI operation idempotency and replay

Validation-only command:

```bash
pytest -q tests/test_ai_operation_idempotency.py
```

Expected: one provider call for a successful replay, payload conflict rejection, stale-owner protection, sanitized timeout recovery, and blocked `AMBIGUOUS` retry. Evidence: [retry-safety case study](CASE_AI_RETRY_SAFETY.md).

Optional real-infrastructure command, only after independently verifying that `DATABASE_URL` points to the disposable `automotive_verify` database and `REDIS_TEST_URL` points to a dedicated test Redis database:

```bash
pytest -q -m postgres tests/integration/test_postgres_ai_operation_idempotency.py
pytest -q -m redis tests/integration/test_postgres_ai_operation_idempotency.py
```

The tests use unique operation IDs and Redis namespaces and delete only their own Redis keys. Never run `FLUSHDB`, `FLUSHALL`, or a database reset.

## 4. Corrected RCA metrics and BLOCK gates

Commands:

```bash
pytest -q tests/test_rca_metric_integrity.py tests/test_ai_value_review_completeness.py
python scripts/export_landing_data.py
pytest -q tests/test_landing_data.py
python -c "import json; d=json.load(open('docs/portfolio/data/rca_metrics_v2.json')); print(d['scoring_version'], d['corrected_v2']['evidence_support_rate'], d['corrected_v2']['unsupported_claim_rate'], d['corrected_v2']['quality_gate'])"
```

Expected final line:

```text
rca-metrics-v2 0.133333 0.766667 BLOCK
```

The exporter updates only recruiter-facing derived data. It does not modify `artifacts/ai_value/rca_report.json`, reviews, thresholds, or the manifest.

## 5. CI and release decision

- Open [GitHub Actions run 43178347023](https://github.com/lichangqing1/automotive-work-order-intelligence/actions/runs/43178347023).
- Confirm the completed `quality`, `dependency-security`, `container`, and `landing` jobs.
- Review the [C1 security release gate](../reports/C1_SECURITY_RELEASE_GATE.md).

Expected interpretation: application duplicate-execution P1 is closed within tested guarantees; local and isolated verification are `GO`; controlled synthetic staging is `CONDITIONAL GO`; shared and production deployment are `NO-GO`.

## Optional landing verification

With Node 22 and pnpm 10:

```bash
cd landing
pnpm install --frozen-lockfile
pnpm lint
pnpm test
```

This builds and server-renders the bilingual site. It does not deploy it.

## Demonstration cleanup

Validation-only steps require no cleanup. Leave existing containers, databases, and Redis services running as found. Remove only explicitly created local scratch files; do not delete application data or historical evidence.
