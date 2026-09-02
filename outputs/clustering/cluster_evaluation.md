# Phase 7 cluster evaluation

## Merge safety

Accepted components imply **99,372** merged record pairs. **99,372** are true same-entity pairs and **0** are false merges.
Pairwise cluster precision is **100.0000%**. Pairwise recall across all hidden same-entity record pairs is **69.4351%**; human-record recall is **65.3699%**.

## Cluster purity

Accepted merged components: **57,403**; mixed-person accepted components: **0**; largest number of hidden entities in one accepted component: **1**.

## Canonical-link outcomes

| Outcome | Links |
|---|---|
| total links | 99,000 |
| accepted cluster links | 64,499 |
| quarantined together links | 0 |
| not merged links | 34,501 |
| recoverable accepted cluster links | 64,499 |
| recoverable quarantined together links | 0 |
| recoverable not merged links | 23,656 |

## Hard-negative transitivity

Of **20,000** explicit hard negatives, **0** end in one accepted cluster, **0** occur together only in quarantine, and **20,000** remain apart.

## Rule 1 quarantine contents

Rule 1 quarantined **0** components containing **0** records and **0** distinct hidden entities in aggregate.
No component exceeded the cap, so the quarantine is empty.

## Interpretation

Overall accuracy is intentionally omitted. Cluster precision is the primary safety metric because one false edge can contaminate an entire transitive component. Automated entities remain in the operational count; removing bots or QA traffic requires a separately validated policy rather than hidden labels.
