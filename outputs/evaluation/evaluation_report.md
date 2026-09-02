# Phase 12 consolidated evaluation and error analysis

## Executive conclusion

The selected logistic resolver auto-merges **29,124** frozen-test candidate pairs with **0 observed false auto-merges**, giving **100.0000% observed precision**. Auto recall is **74.2751%** and increases to **88.3834%** when true matches routed to review are included.

This is observed performance on the synthetic fixture, not a guarantee of perfect production precision. Overall accuracy is intentionally omitted; precision and recall are reported separately.

## Pipeline loss attribution

Blocking retains all **88,155** recoverable canonical links and loses none before scoring. The **10,105** blocked canonical links are deliberately unrecoverable under the usable-evidence definition. Pair scoring and conservative decision bands—not candidate discovery—therefore account for the remaining recoverable links that are not automatically resolved.

Final clustering accepts **64,499** recoverable canonical links and leaves **23,656** unresolved. It produces zero mixed-person clusters and connects 0/20,000 explicit hard negatives.

## Frozen-test subgroup findings

Lowest auto-recall source pairs with at least one true match:

| Source pair | True matches | Auto recall | Assisted recall | False auto-merges |
|---|---:|---:|---:|---:|
| social_logins+ticketing | 6,523 | 59.2519% | 79.8866% | 0 |
| app_users+ticketing | 18,068 | 59.7687% | 82.3777% | 0 |
| ticketing+ticketing | 1,190 | 86.6387% | 95.0420% | 0 |
| app_users+store_customers | 1,504 | 99.9335% | 100.0000% | 0 |
| app_users+app_users | 1,316 | 100.0000% | 100.0000% | 0 |

Identifier availability is measured from valid normalized endpoint fields, not inferred from disagreement:

| Identifier family | State | Candidate pairs | Auto recall | Assisted recall |
|---|---|---:|---:|---:|
| email | both_present | 57,635 | 74.5543% | 88.5265% |
| email | neither_present | 16 | 100.0000% | 100.0000% |
| phone | both_present | 31,507 | 99.8924% | 100.0000% |
| phone | neither_present | 15,746 | 89.0182% | 95.0629% |

## Error analysis

There are no observed false auto-merges to characterize in the frozen test. Error analysis therefore focuses on false negatives: **5,532** true matches enter review and **4,555** remain separate. The supporting unresolved-pattern table groups these cases by decision, source pair, evidence signature and conflicts without exposing record or person identifiers.

Hard-negative results are reported by scenario, including blocked cases. A zero false-auto-merge result on curated scenarios is a safety check, not a substitute for the general non-match precision denominator.

## Calibration and decision bands

The frozen-test Brier score is **0.062639**, log loss is **0.194626**, and ten-bin expected calibration error is **0.015856**. The score-band table reports mean predicted probability and observed match rate separately for validation and frozen test. No post-hoc calibration transform or threshold tuning is performed in Phase 12. The assessment's 0.88/0.62 boundaries remain unchanged.

## Operational review context

The full selected run contains **20,560** review pairs. Frozen-test review yield is **88.7677%**; applying that rate mechanically to the full queue suggests about **18,251** true-match reviews. This is a workload-planning projection for Phase 13, not a final customer-count adjustment, because review pairs can overlap transitively and production distribution may differ.

## Isolation and limitations

- Subgroup/error conclusions use the person-disjoint frozen test; development rows do not support those conclusions.
- Labels are opened only after scoring and clustering artifacts are frozen.
- No model coefficient, calibration transform, threshold, candidate rule or cluster is modified.
- Evidence-event subgroups overlap when a pair has multiple evidence items.
- Synthetic outcomes may be more separable than future production data and do not measure distribution shift.
- The operational identity count still includes automated/test traffic.

Supporting CSV files contain the complete subgroup and loss-attribution measurements used by this report.
