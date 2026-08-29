# Phase 6 Merge Confidence Threshold Scoring Report

**Project:** Kestrel Identity Resolution

**Assessment:** Tailwyndz Propel Lateral Drive 2026 - Assessment No. 6

**Report date:** 30 August 2026

**Phase status:** Complete with corrected person-disjoint evaluation

## Executive summary

Phase 6 assigned an explainable Merge Confidence Threshold (MCT) score to every one of the
204,547 Phase 5 candidate pairs. The assessment's fixed decision bands were applied exactly:

- MCT at least 0.88: auto-merge edge;
- MCT from 0.62 up to but not including 0.88: human review; and
- MCT below 0.62: leave separate.

The corrected person-disjoint frozen 30% test partition contains 59,727 candidate pairs. It
produces **23,824 auto-merges with 100.0000% precision**, 60.7585% auto-merge recall within
candidates, and 74.1603% recall when true matches sent to review are included. No explicit
hard negative auto-merges in development, validation, test or the complete 20,000-pair
hard-negative manifest.

Phase 6 does not perform transitive merging. Its 81,041 auto-merge decisions are edges for
Phase 7, where Rule 1's 12-record component cap is applied.

## Scoring design

Evidence weights reflect identifier strength and the assessment's asymmetric privacy cost.
A same-source repeated record key, account reference or provider ID is strong. A verified
email can cross the auto-merge threshold alone. Ordinary email and phone are review-strength
alone; independent corroboration can move them above 0.88. Device, payment-token and name
composites remain weaker because the dataset contains shared labs, households and common
names.

Only the strongest feature in each correlated family contributes. For example, exact email,
email skeleton and the SHA-256 bridge are one email family rather than three independent
confirmations. Independent family strengths use noisy-OR:

`positive score = 1 - product(1 - strongest family strength)`

Documented conflict penalties are subtracted and safety caps are applied. The final value is
bounded from 0 to 1. Every selected feature, conflict, positive score, penalty, final score
and decision is written for each candidate pair.

## Rule 2 enforcement

The scorer loads the post-normalization registry of 2,057 values occurring on more than 40
physical records. Those values are removed before agreement and conflict features are
calculated, so they contribute neither positive nor negative weight.

## Original split audit and correction

The initial evaluator partitioned physical pairs independently. A post-hoc leakage audit
found that 35,279 of 104,994 candidate endpoint people appeared in multiple partitions, a
33.6010% overlap rate. That design was rejected before the ML challenger. The measured
finding remains in [the partition leakage audit](phase_6_partition_leakage_audit.md).

The corrected evaluator constructs a hidden-person relationship graph only after production
scores exist. Every scored candidate edge and every explicit hard-negative edge connects its
endpoint people. Complete graph components are then assigned by salted SHA-256:

| Partition | Hash buckets | Intended use |
|---|---:|---|
| Development | 0-49 | Diagnose rules or train a challenger |
| Validation | 50-69 | Select and calibrate without opening the test set |
| Frozen test | 70-99 | Final reported holdout metrics |

Every person belongs to exactly one component and therefore exactly one partition. All
204,547 candidate pairs are retained, no outcome-based resampling is used, and no person ID
is written to a labelled artifact. The production scoring file and configuration existed
before labels were opened.

## Development calibration

The first development pass found one auto-merged hard negative: two people sharing an
ordinary household email and payment token. A general household-risk cap moved that
combination to review unless another independent family exists. A review-only floor was then
added for usable email/phone evidence with ordinary contradictions. Verified-email or
account-reference contradictions disqualify this floor.

The scoring configuration was frozen before validation and test labels were released.
Correcting the evaluation split did not change a production score, pair decision or cluster.

## Pair-level results

| Partition | Candidates | Auto-merges | Merge precision | Auto recall | Review queue | Auto + review recall |
|---|---:|---:|---:|---:|---:|---:|
| Development | 103,763 | 41,109 | 100.0000% | 61.2078% | 11,274 | 74.9460% |
| Validation | 41,057 | 16,108 | 100.0000% | 60.4745% | 4,499 | 74.0276% |
| **Frozen test** | **59,727** | **23,824** | **100.0000%** | **60.7585%** | **6,490** | **74.1603%** |
| Full candidate population | 204,547 | 81,041 | 100.0000% observed | - | 22,263 | - |

Overall accuracy is not reported because obvious non-matches dominate the possible-pair
universe.

## End-to-end canonical-link results

Across all 99,000 canonical links:

| Outcome | Links |
|---|---:|
| Auto-merge | 51,134 |
| Human review | 13,427 |
| Leave separate after scoring | 24,334 |
| Blocked before scoring | 10,105 |

End-to-end auto-merge recall is 51.6505%, and auto-merge-plus-review recall is 65.2131%.
Among the 88,155 links labelled recoverable, auto-merge recall is 58.0047% and assisted
recall is 73.1689%.

## Hard-negative safety

| Hard-negative scenario | Total | Auto-merge | Review | Separate | Blocked |
|---|---:|---:|---:|---:|---:|
| Common name and city | 4,000 | 0 | 5 | 3,957 | 38 |
| Couple sharing email and payment | 4,000 | 0 | 4,000 | 0 | 0 |
| Father and son | 4,000 | 0 | 64 | 3,893 | 43 |
| University computer lab | 8,000 | 0 | 0 | 6,202 | 1,798 |
| **Total** | **20,000** | **0** | **4,069** | **14,052** | **1,879** |

Hard negatives sent to review are not false merges. They show that the review band captures
ambiguous household and family cases while the automatic path remains clean on the fixture.

## Labelled pair sets

The local `labelled_development_set.csv.gz`, `labelled_validation_set.csv.gz` and
`labelled_test_set.csv.gz` contain 103,763, 41,057 and 59,727 pairs respectively. They include
pair identity, blocking rules, selected evidence, conflicts, MCT score, decision, truth
label and optional hard-negative type. Hidden person identifiers are never written.

The row-level files are excluded from Git. Their deterministic hashes and row counts are
recorded in the committed evaluation JSON.

## Verification and isolation

- Production scoring references no truth map, canonical links, hard negatives, person IDs,
  scenario types or evidence-mode labels.
- The exact 0.88 and 0.62 bands are enforced by configuration validation and tests.
- Rule 2 values contribute zero positive and negative weight.
- Correlated features cannot be double-counted.
- Every candidate is scored exactly once, and compressed outputs are deterministic.
- All 308,400 hidden entities occur in exactly one model partition; measured overlap is zero.
- The 281,183 relationship components have a maximum size of 35 people.
- Every one of the 204,547 scored candidate pairs is retained in exactly one partition.
- No cluster or transitive merge is formed in Phase 6.

## Limitations and next phase

The weights are defensible rules, not probabilities learned from real customer outcomes.
Frozen-test performance measures the deterministic synthetic fixture and is not a guarantee
of production performance. Human review workload remains 22,263 pairs.

The corrected development and validation sets now provide a leakage-safe basis for the
optional Phase 9 interpretable logistic-regression challenger. The frozen test must remain
unopened during challenger training and selection.
