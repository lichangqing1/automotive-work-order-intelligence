# AI value evaluation protocol

## Claim boundary

This project does not claim that the presence of an LLM improves quality. A
claim is permitted only when the same versioned cases are run through the
deterministic/human baseline and AI-assisted conditions, the output is reviewed
by a human, and the immutable report is marked publishable.

## Test-generation experiment

1. Record human-only active design time and validated scenario coverage for
   every requirement in the declared benchmark in JSONL.
2. Run the OpenAI condition three times with a fixed model and prompt v2.
3. Blind-review every deterministic-baseline and AI-generated case using the
   same judgment process. Confirm coverage labels, record unchanged, edited, or
   rejected, select rejection reasons, and record active review time.
4. Score the exact immutable run with `--score-run`, `--reviews`, and
   `--human-baseline`. The model is not called again. Generation latency is
   included in end-to-end time but excluded from human effort.

## RCA experiment

The deterministic and AI conditions receive identical evidence IDs and facts.
Evaluation scores failure class, known root cause, citation validity, evidence
correctness against `supporting_evidence_ids`, unsupported claims, and correct
abstention. Reviewers separately score
recommended-check usefulness and record matched investigation time. Claims
citing unknown or irrelevant evidence IDs count as unsupported.

## Publication completeness

The runner marks a report publishable only when it is a `--score-run` of an
immutable OpenAI experiment. Test generation requires exactly one review for
every baseline and AI-generated test, plus exactly one human-only measurement
for every requirement. RCA requires exactly one review for every case and run.
Any missing, duplicate, or unexpected record blocks publication. Supplying a
review filename alone is never sufficient.

## Reproducibility and governance

Every run records its provider, model, prompt version, dataset version and SHA,
run count, raw structured output, statistical summary, and gate result. Output
directories use unique experiment IDs and are never overwritten. Persisted
experiments use `EvaluationRun` and `EvaluationMetric`; the dashboard reads the
same records through `/api/v1/ai-value/experiments`.

The initial policy file is explicitly marked `proposed_until_calibrated`.
Thresholds become approved only after real benchmark data and business review.
Mock-provider output can test schemas and orchestration but cannot pass value
gates or support an improvement claim.

## Reporting

Report N, mean, median, population standard deviation, minimum, and maximum.
Show baseline and AI values plus per-metric differences. AI is not required to
win every metric; duplicate, unsupported-claim, and abstention regressions must
remain visible. Never manually enter a headline percentage.
