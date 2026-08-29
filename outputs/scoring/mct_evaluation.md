# Phase 6 MCT evaluation

## Pair-level results

| Partition | Candidates | Auto-merges | Merge precision | Merge recall | Review queue | Auto + review recall |
|---|---|---|---|---|---|---|
| development | 103,763 | 41,109 | 100.0000% | 61.2078% | 11,274 | 74.9460% |
| validation | 41,057 | 16,108 | 100.0000% | 60.4745% | 4,499 | 74.0276% |
| test | 59,727 | 23,824 | 100.0000% | 60.7585% | 6,490 | 74.1603% |

Overall accuracy is intentionally not reported because obvious non-matches dominate the universe of possible pairs.

## End-to-end canonical-link result

Across the released evaluation scope, **51,134** canonical links auto-merge, **13,427** enter review, **24,334** remain separate after scoring, and **10,105** were blocked before scoring.
End-to-end auto-merge recall is **51.6505%** and auto-merge-plus-review recall is **65.2131%**.

## Safety result

Of **20,000** explicit hard negatives, **0** auto-merge, **4,069** enter review, **14,052** remain separate, and **1,879** never became candidates.
The explicit-hard-negative false auto-merge rate is **0.0000%**.

## Labelled test-set design

Hidden people connected by any scored candidate or explicit hard-negative relationship are first grouped into complete isolation components. Each component is assigned by a stable salted SHA-256 hash to 50% development, 20% validation or 30% frozen-test buckets. This retains every scored candidate while preventing one person from occurring in multiple model partitions. Outcomes are not used for assignment, and person identifiers are not written to labelled artifacts.

## Person-isolation proof

The split contains **308,400** hidden entities in **281,183** isolation components. The largest component contains **35** people. All **204,547** scored candidate edges were retained, and measured person overlap across model partitions is **0**.

## Isolation

The MCT configuration and scored-pair file existed before labels were opened. This evaluator cannot alter production scores or decisions. Final mode releases the validation and frozen-test metrics; development mode exposes only development metrics.
