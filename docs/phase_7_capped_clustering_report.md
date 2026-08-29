# Phase 7 Capped Transitive Clustering Report

**Project:** Kestrel Identity Resolution

**Assessment:** Tailwyndz Propel Lateral Drive 2026 — Assessment No. 6

**Report date:** 30 August 2026
**Phase status:** Complete and independently evaluated

## Executive summary

Phase 7 converted the 81,041 Phase 6 auto-merge pair decisions into connected identity
components and enforced the assessment's Rule 1 exactly. Components of up to 12 physical
source records were accepted. Components of 13 or more would receive no final cluster ID
and would be rejected and quarantined in full.

The full run produced **355,762 connected components** from 420,000 physical records. No
component exceeded the cap; the largest contained six records. Truth-based evaluation found
**81,863 implied merged record pairs, 100.0000% pairwise cluster precision, zero mixed-person
accepted components, and zero transitive hard-negative merges**.

The resulting 355,762 is an operational resolved-identity-record count, not yet a defensible
count of real customers. It includes automated entities and treats unresolved review/separate
pairs conservatively. The hidden synthetic truth contains 300,000 humans and 8,400 distinct
automated entities.

## Rule 1 implementation

Only pairs labelled `auto_merge` by Phase 6 participate in union-find. Human-review and
leave-separate pairs are counted but cannot create edges.

After all auto-merge edges are unioned transitively, the complete connected component is
measured:

- sizes 1–12 are accepted;
- size 13 or larger is rejected in full;
- every record in an oversized component has an empty final cluster ID;
- none of its internal edges are retained as partial merges; and
- the 0.88 MCT threshold is never changed to make a component fit.

This order matters. Checking component size edge by edge could accept an arbitrary partial
tree and would violate the assessment.

## Production results

| Metric | Result |
|---|---:|
| Physical source records | 420,000 |
| Auto-merge edges consumed | 81,041 |
| Proposed connected components | 355,762 |
| Accepted merged components | 48,814 |
| Accepted singleton components | 306,948 |
| Records collapsed by accepted merges | 64,238 |
| Rule 1 quarantined components | 0 |
| Quarantined records | 0 |
| Rejected auto-merge edges | 0 |
| Partial merges from quarantine | 0 |
| Threshold adjustments | 0 |
| Final resolved identity records | 355,762 |

There are more auto-merge edges than collapsed records because some components contain
cycles and redundant corroborating edges. The accepted components imply 81,863 pairwise
relationships after transitive closure.

## Component-size distribution

| Component size | Components | Records |
|---:|---:|---:|
| 1 | 306,948 | 306,948 |
| 2 | 34,700 | 69,400 |
| 3 | 13,498 | 40,494 |
| 4 | 119 | 476 |
| 5 | 300 | 1,500 |
| 6 | 197 | 1,182 |

No component has size 7–12, and no component exceeds 12.

## Largest component

The largest component contains six records belonging to one hidden entity:

| Source | Records |
|---|---:|
| App users | 1 |
| Ticketing | 1 |
| Social logins | 4 |

Its 15 internal auto-merge edges use exact device, phone, verified-email, ordinary-email and
name-and-city evidence. It was accepted because six is below the cap and post-clustering
evaluation confirmed that all members belong to one hidden entity.

The absence of a cap hit does not make Rule 1 unnecessary. It demonstrates that Rule 2,
candidate blocking and conservative MCT scoring prevented the poisoned transitive collapse
seen in the naive 104,136-record component.

## Truth-based cluster evaluation

| Metric | Result |
|---|---:|
| Predicted merged record pairs | 81,863 |
| True-positive merged pairs | 81,863 |
| False-positive merged pairs | 0 |
| Pairwise cluster precision | 100.0000% |
| Recall across all hidden entity pairs | 57.2009% |
| Recall across human true pairs | 51.5085% |
| Mixed-person accepted components | 0 |
| Maximum hidden entities in an accepted component | 1 |

Precision is the primary safety metric. Recall remains intentionally lower because
human-review edges are not silently accepted and zero-evidence or conflicted links stay
separate.

## Canonical-link outcomes

| Outcome | Links |
|---|---:|
| Accepted in one final cluster | 51,576 |
| Together only in quarantine | 0 |
| Not merged | 47,424 |
| **Total** | **99,000** |

All 51,576 merged canonical links are among the links labelled recoverable. No recoverable
link was blocked in Phase 5, but 36,579 recoverable links remain unresolved because their MCT
evidence was not strong enough for auto-merge.

## Hard-negative transitivity

All **20,000 explicit hard-negative pairs remain apart** after transitive clustering:

- common name and city: 4,000/4,000 apart;
- couples sharing email and payment: 4,000/4,000 apart;
- fathers and sons: 4,000/4,000 apart; and
- university computer lab: 8,000/8,000 apart.

This verifies that no third record created a hidden transitive path between endpoints that
were safe at pair level.

## Reproducibility and isolation

- Every physical normalized record is assigned exactly once.
- Component IDs hash the sorted member identities and are deterministic.
- Repeated fixtures produce byte-identical compressed assignment output.
- The clusterer validates that every auto-merge score is at least 0.88 and every review or
  separate score lies in its required band.
- Production clustering contains no truth-map, canonical-link, hard-negative, person-ID,
  scenario or evidence-mode dependency.
- The separate evaluator joins hidden labels only after assignments and hashes exist.
- Overall accuracy is not reported.

## Handoff

The technical matching pipeline is now complete through capped clustering. The remaining
assessment work is to turn these results into a defensible business count and range,
prioritise or cost the 22,263-pair review queue, decide how automated/QA traffic is handled
without using hidden labels, and prepare the two-page memo and presentation deck.
