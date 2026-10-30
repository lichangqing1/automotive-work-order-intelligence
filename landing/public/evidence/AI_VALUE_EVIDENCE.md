# AI value evidence

## Table of contents

1. [Purpose](#purpose)
2. [Claim boundary](#claim-boundary)
3. [Evaluation design](#evaluation-design)
4. [Experiment inventory](#experiment-inventory)
5. [Test-generation results](#test-generation-results)
6. [RCA results](#rca-results)
7. [Improvements and regressions](#improvements-and-regressions)
8. [Interpretation and limitations](#interpretation-and-limitations)
9. [Reproducibility](#reproducibility)
10. [Privacy and sanitization](#privacy-and-sanitization)
11. [Artifact manifest](#artifact-manifest)
12. [Final conclusion](#final-conclusion)

## Purpose

This package contains aggregate, sanitized evidence from the controlled `ai-value-v1` benchmark. It compares deterministic baselines with AI-assisted test generation and root-cause analysis using the same versioned inputs.

## Claim boundary

Both experiments used the OpenAI provider, prompt version `v2`, model `gpt-5-mini`, and three runs. Both immutable source experiments were rescored with complete human review and are marked `publishable: true`. Publication eligibility means the evidence is complete; it does not mean every quality threshold passed or that AI is universally superior.

## Evaluation design

Test generation uses 30 requirements and measures validated scenario coverage, approval and rejection outcomes, unsupported assumptions, execution quality, and time. RCA uses 30 evidence bundles and measures evidence support, unsupported claims, abstention, root-cause accuracy, recommended-check usefulness, and investigation time. The policy thresholds remain `proposed_until_calibrated`.

## Experiment inventory

| Experiment | Scored experiment | Source experiment | Reviews | Publishable | Quality gates |
| --- | --- | --- | ---: | --- | --- |
| Test generation | `EXP-20261028T140042Z-D1B9B4C5` | `EXP-20261022T044058Z-2E53566B` | 1,122/1,122 | Yes | BLOCK |
| RCA | `EXP-20261029T132933Z-4731BD11` | `EXP-20261028T141922Z-AEB083B0` | 90/90 | Yes | BLOCK |

## Test-generation results

| Metric | Baseline mean | AI mean | AI minus baseline |
| --- | ---: | ---: | ---: |
| Requirement coverage | 5.83% | 49.35% | +43.52 pp |
| Negative coverage | 20.00% | 47.96% | +27.96 pp |
| Boundary coverage | 50.00% | 66.67% | +16.67 pp |
| Integration coverage | 46.67% | 60.00% | +13.33 pp |
| Data-quality coverage | 66.67% | 81.67% | +15.00 pp |
| Approval rate | 6.67% | 39.58% | +32.92 pp |
| Unsupported-assumption rate | 0.00% | 100.00% | +100.00 pp |

Human-effort saving was 48.98%, and end-to-end time saving was 19.00%. The proposed quality policy returned `BLOCK`: schema validity, executable rate, and duplicate rate passed; requirement coverage, negative coverage, unsupported-assumption rate, and approval rate failed their thresholds.

## RCA results

| Metric | Baseline mean | AI mean | AI minus baseline |
| --- | ---: | ---: | ---: |
| Active investigation time | 77.60 s | 49.41 s | -28.19 s |
| Evidence-support rate | 100.00% | 94.52% | -5.48 pp |
| Unsupported-claim rate | 0.00% | 5.48% | +5.48 pp |
| Correct abstention | 16.67% | 13.33% | -3.33 pp |
| Failure-class accuracy | 36.67% | 0.00% | -36.67 pp |
| Root-cause accuracy | 20.00% | 0.00% | -20.00 pp |
| Recommended-check usefulness | n/a | 75.56% | n/a |

The proposed RCA policy returned `BLOCK`. Evidence support passed, while unsupported claims, correct abstention, and root-cause accuracy failed their thresholds.

## Improvements and regressions

AI-assisted test generation increased reviewed coverage and reduced measured human and end-to-end effort. AI-assisted RCA reduced investigation time and its recommended checks received a 75.56% usefulness score. Material regressions remain: every generated test recorded at least one unsupported assumption, and RCA accuracy and abstention were worse than the deterministic baseline. These regressions are retained in the evidence and are not averaged away.

## Interpretation and limitations

The benchmark is a controlled portfolio evaluation, not a production causal study. It uses 30 curated cases per experiment, one model, one prompt version, and one human review process. The proposed thresholds have not been business-calibrated. Results support metric-specific conclusions only and do not establish universal AI superiority.

## Reproducibility

The source reports record experiment IDs, provider, model, prompt and dataset versions, dataset hashes, run counts, completeness checks, aggregates, differences, and policy results. The sanitized JSON reports retain those fields without raw outputs or reviewer-level records. `manifest.json` records source and artifact SHA-256 hashes.

## Privacy and sanitization

This directory excludes credentials, environment files, Jira configuration, raw model outputs, review workbooks, individual review records, timings tied to individual reviewers, and reviewer identities. Only aggregate reports and reproducibility metadata are included.

## Artifact manifest

`manifest.json` identifies both immutable source reports and their sanitized copies. Re-run `python scripts/publish_ai_value_artifacts.py` after an explicitly approved source-report change, then repeat the secret scan and test suite.

## Final conclusion

Both experiments satisfy publication-completeness requirements. The measured evidence shows useful gains and significant regressions, and both proposed quality policies currently return `BLOCK`. The project therefore demonstrates a reproducible evaluation system and an honest metric-by-metric result, not an unqualified claim that AI improves every testing outcome.
