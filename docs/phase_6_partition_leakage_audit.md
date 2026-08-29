# Phase 6 Pair-Partition Leakage Audit

**Audit date:** 30 August 2026

**Status:** Pre-fix finding retained as development evidence

## Question

The first Phase 6 evaluator assigned candidate pairs to development, frozen-test and audit
partitions by hashing the physical pair identity. This was deterministic and kept hidden
labels out of production scoring, but it did not establish that one hidden person occurred
in only one evaluation partition.

This audit joined the already-created scored pairs to `person_map.csv` inside the isolated
evaluator boundary and counted the partitions in which each candidate endpoint person
appeared. It did not alter scores or decisions.

## Measured result

| Metric | Result |
|---|---:|
| Scored candidate pairs | 204,547 |
| People represented by candidate endpoints | 104,994 |
| People appearing in exactly one partition | 69,715 |
| People appearing in two partitions | 21,657 |
| People appearing in all three partitions | 13,622 |
| People appearing in multiple partitions | 35,279 |
| Person-overlap rate | 33.6010% |
| People with at least one positive candidate pair | 73,295 |
| Positive-pair people appearing in multiple partitions | 22,205 |

The old pair-hash counts were:

| Partition | Candidate pairs | True matches | True non-matches |
|---|---:|---:|---:|
| Development | 102,514 | 66,708 | 35,806 |
| Frozen test | 61,206 | 39,754 | 21,452 |
| Audit | 40,827 | 26,548 | 14,279 |

## Decision

The pair-hash split is rejected as the labelled-test design for machine-learning
comparison. It remains valid only as historical descriptive evidence of how the rule-based
score behaved on deterministic pair subsets.

The replacement will:

1. hash hidden person identity only inside the post-scoring evaluator;
2. assign each person to one development, validation or frozen-test partition;
3. retain a labelled pair in a model partition only when both endpoints belong to that
   partition;
4. report different-person pairs whose endpoints cross partitions as a separate safety
   cohort, never as training, validation or frozen-test data;
5. keep all explicit hard negatives in a separate full-population safety audit;
6. write no person identifier into publishable labelled pair artifacts; and
7. prove zero person overlap with automated tests and output metadata.

This correction does not change candidate blocking, MCT features, MCT scores, decisions or
Rule 1 clusters. It changes only the isolated labelled evaluation design.
