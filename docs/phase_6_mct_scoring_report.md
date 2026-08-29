# Phase 6 Merge Confidence Threshold Scoring Report

**Project:** Kestrel Identity Resolution  
**Assessment:** Tailwyndz Propel Lateral Drive 2026 — Assessment No. 6  
**Report date:** 30 August 2026  
**Phase status:** Complete; clustering intentionally deferred

## Executive summary

Phase 6 assigned an explainable Merge Confidence Threshold (MCT) score to every one of the
204,547 Phase 5 candidate pairs. The assessment's fixed decision bands were applied exactly:

- MCT at least 0.88: auto-merge edge;
- MCT from 0.62 up to but not including 0.88: human review; and
- MCT below 0.62: leave separate.

The frozen 30% test partition contained 61,206 candidate pairs. It produced **24,369
auto-merges with 100.0000% precision**, 61.2995% auto-merge recall within candidates, and
74.7950% recall when true matches sent to review are included. No explicit hard negative
auto-merged in development, test, audit or the full 20,000-pair hard-negative manifest.

Phase 6 does not perform transitive merging. The auto-merge labels are edges for the next
phase, where Rule 1's 12-record component cap must be applied.

## Scoring design

Evidence weights were chosen to reflect identifier strength and the assessment's asymmetric
privacy cost. A same-source repeated record key, account reference or provider ID is strong.
A verified email can cross the auto-merge threshold alone. Ordinary email and phone are
review-strength alone; independent corroboration can move them above 0.88. Device,
payment-token and name composites remain weaker because the synthetic data deliberately
contains shared labs, households and common names.

Only the strongest feature in each correlated family contributes. For example, exact email,
email skeleton and the SHA-256 bridge are one email family, not three confirmations.
Independent family strengths use noisy-OR:

`positive score = 1 - product(1 - strongest family strength)`

Documented conflict penalties are subtracted and safety caps are applied. The final value is
bounded from 0 to 1. Every selected evidence feature, conflict, positive score, penalty,
final score and decision is written for each candidate pair.

## Rule 2 enforcement

The scorer loads the post-normalization registry of 2,057 values occurring on more than 40
physical records. Such values are removed before both agreement and conflict features are
calculated, so they contribute neither positive nor negative weight and cannot re-enter the
score through an exact feature.

## Development calibration and frozen holdout

Candidate pairs are partitioned by SHA-256 of stable pair identity:

| Partition | Hash buckets | Intended use |
|---|---:|---|
| Development | 0–49 | Diagnose and calibrate general safety rules |
| Frozen test | 50–79 | Final reported pair metrics |
| Audit | 80–99 | Stability check |

No outcome-based resampling is used, so each partition preserves the natural candidate
prevalence. The scoring file and configuration hash exist before labels are opened.

The first development pass found one auto-merged hard negative: two people sharing an
ordinary household email and payment token. A general household-risk cap moved that
combination to review unless another independent family exists. A review-only floor was
then added for usable email/phone evidence with ordinary contradictions; it improved
assisted recall without increasing auto-merges. Verified-email or account-reference
contradictions disqualify this floor. The configuration was frozen before the test and audit
partitions were released.

## Pair-level results

| Partition | Candidates | Auto-merges | Merge precision | Auto recall | Review queue | Auto + review recall |
|---|---:|---:|---:|---:|---:|---:|
| Development | 102,514 | 40,581 | 100.0000% | 60.8338% | 11,134 | 74.4304% |
| **Frozen test** | **61,206** | **24,369** | **100.0000%** | **61.2995%** | **6,629** | **74.7950%** |
| Audit | 40,827 | 16,091 | 100.0000% | 60.6110% | 4,500 | 74.3860% |
| Full candidate population | 204,547 | 81,041 | 100.0000% observed | — | 22,263 | — |

Overall accuracy is not reported because the assessment explicitly rejects it and obvious
non-matches dominate the possible-pair universe.

## End-to-end canonical-link results

Across all 99,000 canonical links:

| Outcome | Links |
|---|---:|
| Auto-merge | 51,134 |
| Human review | 13,427 |
| Leave separate after scoring | 24,334 |
| Blocked before scoring | 10,105 |

End-to-end auto-merge recall is 51.6505%. Auto-merge plus review recall is 65.2131%.
Among the 88,155 links labelled recoverable, auto-merge recall is 58.0047% and assisted
recall is 73.1689%. This is deliberately conservative: missed matches cause duplicate
communications, whereas false merges can expose another person's orders, tickets or address.

## Hard-negative safety

| Hard-negative scenario | Total | Auto-merge | Review | Separate | Blocked |
|---|---:|---:|---:|---:|---:|
| Common name and city | 4,000 | 0 | 5 | 3,957 | 38 |
| Couple sharing email and payment | 4,000 | 0 | 4,000 | 0 | 0 |
| Father and son | 4,000 | 0 | 64 | 3,893 | 43 |
| University computer lab | 8,000 | 0 | 0 | 6,202 | 1,798 |
| **Total** | **20,000** | **0** | **4,069** | **14,052** | **1,879** |

Hard negatives sent to review are not false merges. They demonstrate that the review band is
catching genuinely ambiguous household or family cases while the auto-merge path remains
clean on the synthetic fixture.

## Labelled test set

The local `labelled_test_set.csv.gz` contains all 61,206 candidate pairs assigned to the
frozen test partition. It includes pair identity, blocking rules, selected evidence,
conflicts, MCT score, decision, truth label and optional hard-negative type. Hidden person
identifiers are never written. The row-level labelled file is intentionally excluded from
Git; its deterministic hash and row count are recorded in the committed evaluation JSON.

## Verification and isolation

- Production scoring references no truth map, canonical link, hard-negative manifest,
  person ID, truth key, scenario type or evidence-mode label.
- The exact 0.88 and 0.62 bands are enforced by configuration validation and tests.
- Rule 2 values contribute zero positive and negative weight.
- Correlated features cannot be double-counted.
- Household email/payment risk, multiple conflicts and review-floor exclusions have focused
  regression tests.
- Every candidate is scored exactly once and the compressed output is deterministic.
- Source record IDs are reconciled across candidate, normalized and evaluation inputs.
- No cluster or transitive merge is formed in Phase 6.

## Limitations and next phase

The weights are defensible rules, not probabilities learned from real customer outcomes.
Frozen-test performance measures the deterministic synthetic fixture and should not be
presented as guaranteed production performance. Human review workload is 22,263 pairs and
needs an operating model or prioritisation strategy.

Phase 7 must take only the auto-merge edges, form connected components, and apply Rule 1
exactly. Any component containing more than 12 source records must be rejected in full and
quarantined. The threshold must not be raised to make an oversized component fit, and the
component must not be partially merged.
