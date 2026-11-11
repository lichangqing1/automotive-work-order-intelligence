# RCA metric integrity v2 comparison

Date: 2026-11-11  
Source experiment: `EXP-20261029T132933Z-4731BD11`  
Corrected scoring version: `rca-metrics-v2`

This report is a separate deterministic rescore of the preserved raw outputs
and 90 human review records. It does not replace or alter the published v1
report, datasets, raw outputs, reviews, manifests, or policy thresholds.

## Completeness and disposition

- RCA reviews: 90/90, with no missing, duplicate, or unexpected identities.
- Test-generation reviews independently rechecked: 1,122/1,122.
- Human-only measurements independently rechecked: 30/30.
- Original RCA policy result: `BLOCK`.
- Corrected RCA policy result: `BLOCK`.
- Test-generation policy result: `BLOCK`.

## RCA metric comparison

| Metric | Original baseline | Corrected baseline | Original AI | Corrected AI |
| --- | ---: | ---: | ---: | ---: |
| Citation validity | 1.000000 | 0.366667 | 1.000000 | 0.900000 |
| Evidence correctness | 1.000000 | 0.366667 | 0.945185 | 0.845185 |
| Evidence support | 1.000000 | 0.366667 | 0.945185 | 0.133333 |
| Unsupported claims | 0.000000 | 0.000000 | 0.054815 | 0.766667 |
| Correct abstention | 0.166667 | 0.166667 | 0.133333 | 0.133333 |
| Failure-class accuracy | 0.366667 | 0.366667 | 0.000000 | 0.000000 |
| Root-cause accuracy | 0.200000 | 0.200000 | 0.000000 | 0.000000 |

The changed evidence metrics are expected. V1 awarded perfect evidence scores
to responses with no structured claims and treated evidence correctness and
claim support as the same citation-level ratio. V2 gives zero evidence scores
to omissions on sufficient-evidence cases, counts duplicate evidence IDs once,
and evaluates claim support separately from citation validity/correctness. It
also prevents an incorrect root-cause assertion from becoming supported merely
by citing an ID from the expected cause's supporting set.

Root-cause means are unchanged for this historical run, but the defect is still
material: the v1 algorithm could award a match for any substring overlap, such
as `version` against `unsupported_software_version`. V2 accepts only normalized
exact labels and benchmark-declared equivalents.

## Interpretation boundary

Evidence correctness verifies membership in the human-authored
`supporting_evidence_ids` set. Evidence support verifies that each structured
assertion has such a citation and that any asserted root cause matches the
benchmark identity. Neither metric proves that arbitrary explanatory prose is
semantically entailed by the cited fact; that remains a human-review question.
