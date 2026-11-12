# Portfolio documentation acceptance

Baseline commit: `719a0bc74e9a50e7829e4fa0cb755cf80f462080`

## Accepted claim set

- The 30,000-row and 1,200-defect result is limited to the controlled synthetic benchmark.
- Historical RCA v1 remains preserved; current portfolio interpretation uses `rca-metrics-v2` (13.33% evidence support, 76.67% unsupported claims, 0% root-cause accuracy).
- Historical and corrected RCA policies are `BLOCK`; test-generation policy is also `BLOCK`.
- GitHub Actions run `43178347023` succeeded at the baseline commit, including required PostgreSQL and Redis gates.
- Redis implements active quota/concurrency protection, not background job execution.
- Durable AI-operation claims prevent tested retry duplication but do not guarantee exactly-once external-provider billing.
- Controlled synthetic staging is `CONDITIONAL GO`; shared and production deployment are `NO-GO`.

## Deliverables

- Bilingual recruiter-facing READMEs.
- Two GitHub-renderable Mermaid diagrams.
- Three evidence-linked engineering case studies.
- Validation-only demonstration guide.
- Versioned corrected RCA portfolio metrics and deterministic landing export.
- Bilingual landing presentation of historical versus corrected RCA evidence.

## Verification record

| Gate | Result |
|---|---:|
| Validation-only documented demo selections | 12 + 24 + 7 + 29 + 1 passed |
| Real PostgreSQL integration | 12 passed, zero skipped |
| Real Redis integration | 4 passed, zero skipped |
| Full pytest | 246 passed, 1 live-Jira skip |
| Landing lint | Passed |
| Landing build and rendered tests | 7 passed |
| Ruff | Passed |
| `pip check` | Passed |
| `pip-audit --local --skip-editable` | No known vulnerabilities; editable project skipped |
| Alembic | `20261112_0006 (head)`; no pending operations |
| Local Markdown links | 78 checked, 0 missing |
| Historical artifact hashes | 3/3 unchanged |
| Historical quality policies | `BLOCK`, `BLOCK` |

The first landing attempt resolved an obsolete system Node 10 runtime and failed during dependency setup. Re-running with the bundled Node 24 runtime satisfied the repository's Node `>=22.13.0` requirement and passed lint, build, and rendered tests. No application container was restarted, no database was reset, Redis was not flushed, and no live Jira or paid provider was contacted.

The working tree intentionally contains only unstaged Phase P1 documentation, landing presentation, deterministic export, and consistency-test changes. Exact status is reported at handoff rather than embedded here as a volatile snapshot.
