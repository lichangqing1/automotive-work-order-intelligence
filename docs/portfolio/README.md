# Portfolio evidence navigation

This directory is the shortest evidence path for an engineering reviewer. Start with the system boundary, choose a case study, follow its source/test links, and reproduce the relevant behavior with synthetic resources.

## Review path

1. [Architecture and protected AI lifecycle](ARCHITECTURE.md)
2. Engineering case:
   - [Data quality and reconciliation](CASE_DATA_QUALITY.md)
   - [RCA metric integrity](CASE_RCA_METRIC_INTEGRITY.md)
   - [AI operation retry safety](CASE_AI_RETRY_SAFETY.md)
3. [Safe demonstration guide](DEMO_GUIDE.md)
4. [Documentation and demonstration acceptance](ACCEPTANCE_REPORT.md)

## Authoritative evidence

- [AI evaluation protocol](../AI_VALUE_EVALUATION.md)
- [Preserved historical AI-value artifacts](../../artifacts/ai_value/README.md)
- [RCA v2 comparison](../reports/RCA_METRIC_INTEGRITY_V2_COMPARISON.md)
- [Machine-readable corrected RCA portfolio metrics](data/rca_metrics_v2.json)
- [Durable AI-operation contract](../AI_OPERATION_IDEMPOTENCY.md)
- [C1 security release gate](../reports/C1_SECURITY_RELEASE_GATE.md)
- [GitHub Actions run 43178347023](https://github.com/lichangqing1/automotive-work-order-intelligence/actions/runs/43178347023)

## Claims boundary

The 30,000-work-order benchmark is synthetic and controlled. The AI experiments use curated cases and complete human review, but neither quality policy passed. Historical RCA v1 measurements are preserved for provenance; current portfolio-facing RCA interpretation uses `rca-metrics-v2`. Local and isolated engineering verification are `GO`, controlled synthetic staging is `CONDITIONAL GO`, and shared/production deployment remain `NO-GO`.
