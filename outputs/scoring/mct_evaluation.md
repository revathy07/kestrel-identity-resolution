# Phase 6 MCT evaluation

## Pair-level results

| Partition | Candidates | Auto-merges | Merge precision | Merge recall | Review queue | Auto + review recall |
|---|---|---|---|---|---|---|
| audit | 40,827 | 16,091 | 100.0000% | 60.6110% | 4,500 | 74.3860% |
| development | 102,514 | 40,581 | 100.0000% | 60.8338% | 11,134 | 74.4304% |
| test | 61,206 | 24,369 | 100.0000% | 61.2995% | 6,629 | 74.7950% |

Overall accuracy is intentionally not reported because obvious non-matches dominate the universe of possible pairs.

## End-to-end canonical-link result

Across the released evaluation scope, **51,134** canonical links auto-merge, **13,427** enter review, **24,334** remain separate after scoring, and **10,105** were blocked before scoring.
End-to-end auto-merge recall is **51.6505%** and auto-merge-plus-review recall is **65.2131%**.

## Safety result

Of **20,000** explicit hard negatives, **0** auto-merge, **4,069** enter review, **14,052** remain separate, and **1,879** never became candidates.
The explicit-hard-negative false auto-merge rate is **0.0000%**.

## Labelled test-set design

Candidate pairs are assigned by a stable SHA-256 hash to 50% development, 30% frozen test and 20% audit partitions. This preserves the natural candidate prevalence without outcome-based resampling. Person identifiers are used only to create the match/non-match label and are not written to the labelled artifact.

## Isolation

The MCT configuration and scored-pair file existed before labels were opened. This evaluator cannot alter production scores or decisions. Final mode releases the previously hidden test and audit metrics; development mode exposes only development metrics.
