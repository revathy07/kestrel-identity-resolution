# Phase 6 MCT evaluation

## Pair-level results

| Partition | Candidates | Auto-merges | Merge precision | Merge recall | Review queue | Auto + review recall |
|---|---|---|---|---|---|---|
| development | 103,763 | 50,401 | 100.0000% | 75.0428% | 9,456 | 87.4633% |
| validation | 41,057 | 19,740 | 99.9949% | 74.1065% | 3,952 | 87.1565% |
| test | 59,727 | 29,106 | 100.0000% | 74.2292% | 5,818 | 87.3632% |

Overall accuracy is intentionally not reported because obvious non-matches dominate the universe of possible pairs.

## End-to-end canonical-link result

Across the released evaluation scope, **64,408** canonical links auto-merge, **12,334** enter review, **12,153** remain separate after scoring, and **10,105** were blocked before scoring.
End-to-end auto-merge recall is **65.0586%** and auto-merge-plus-review recall is **77.5172%**.

## Safety result

Of **20,000** explicit hard negatives, **0** auto-merge, **635** enter review, **17,486** remain separate, and **1,879** never became candidates.
The explicit-hard-negative false auto-merge rate is **0.0000%**.

## Labelled test-set design

Hidden people connected by any scored candidate or explicit hard-negative relationship are first grouped into complete isolation components. Each component is assigned by a stable salted SHA-256 hash to 50% development, 20% validation or 30% frozen-test buckets. This retains every scored candidate while preventing one person from occurring in multiple model partitions. Outcomes are not used for assignment, and person identifiers are not written to labelled artifacts.

## Person-isolation proof

The split contains **308,400** hidden entities in **281,183** isolation components. The largest component contains **35** people. All **204,547** scored candidate edges were retained, and measured person overlap across model partitions is **0**.

## Isolation

The MCT configuration and scored-pair file existed before labels were opened. This evaluator cannot alter production scores or decisions. Final mode releases development, validation and frozen-test metrics.
