# Phase 7 cluster evaluation

## Merge safety

Accepted components imply **81,863** merged record pairs. **81,863** are true same-entity pairs and **0** are false merges.
Pairwise cluster precision is **100.0000%**. Pairwise recall across all hidden same-entity record pairs is **57.2009%**; human-record recall is **51.5085%**.

## Cluster purity

Accepted merged components: **48,814**; mixed-person accepted components: **0**; largest number of hidden entities in one accepted component: **1**.

## Canonical-link outcomes

| Outcome | Links |
|---|---|
| total links | 99,000 |
| accepted cluster links | 51,576 |
| quarantined together links | 0 |
| not merged links | 47,424 |
| recoverable accepted cluster links | 51,576 |
| recoverable quarantined together links | 0 |
| recoverable not merged links | 36,579 |

## Hard-negative transitivity

Of **20,000** explicit hard negatives, **0** end in one accepted cluster, **0** occur together only in quarantine, and **20,000** remain apart.

## Rule 1 quarantine contents

Rule 1 quarantined **0** components containing **0** records and **0** distinct hidden entities in aggregate.
No component exceeded the cap, so the quarantine is empty.

## Interpretation

Overall accuracy is intentionally omitted. Cluster precision is the primary safety metric because one false edge can contaminate an entire transitive component. Automated entities remain in the operational count; removing bots or QA traffic requires a separately validated policy rather than hidden labels.
