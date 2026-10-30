# AI value benchmark

This dataset supports a controlled comparison of deterministic baselines and
AI-assisted test design/RCA. `requirements.jsonl` contains 30 curated
requirements with human-authored risk and scenario gold labels.
`rca_cases.jsonl` contains 30 evidence bundles, including five deliberate
insufficient-evidence cases. This is the versioned `ai-value-v1` benchmark.

AI-generated coverage tags are claims, not ground truth. The experiment runner
writes a review queue. A quality engineer must record validated coverage,
approval/edit/rejection decisions, rejection reasons, and active review time.
Use `--score-run` with that reviewed file so the exact immutable raw outputs are
scored without another stochastic model call. Only that reviewed score run is
publishable as AI-value evidence. Every generated test from every run must have
exactly one review, including deterministic baseline tests. RCA requires
exactly one review per case and run. Missing, duplicate, or unexpected reviews
keep `publishable` false.

Mock-provider runs are regression checks only. They must never be reported as
evidence that AI improves testing. Real value experiments require the OpenAI
provider, a fixed model, the dataset hash, and at least three runs. The
published evidence is frozen on prompt v2.

Human-only time measurements should be recorded separately on a matched subset.
Do not infer human effort from Jira wall-clock status duration.

The repository intentionally does not contain fabricated review or timing
results. `human_only_measurements.example.jsonl` is a schema example, not
evidence. A publishable test-generation score run requires one real human-only
measurement for every benchmark requirement.

RCA reporting distinguishes citation validity (the evidence ID exists) from
evidence correctness (the cited ID belongs to the human-authored supporting
evidence set). Only evidence correctness contributes to
`evidence_support_rate` and `unsupported_claim_rate`.
