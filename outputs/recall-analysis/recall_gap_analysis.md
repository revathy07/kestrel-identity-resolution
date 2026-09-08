# Development/validation recall-gap analysis

## Isolation contract

This diagnostic reads only the person-disjoint development and validation labelled sets. It does not read the frozen test set, alter a score, change the mandatory 0.88/0.62 thresholds, train a model or emit record/person identifiers.

## Combined finding

Across **93,799** development/validation true candidate matches, **70,148** auto-merge and **12,642** enter review. Automatic recall is **74.7854%** and assisted recall is **88.2632%**. The review band therefore contains an observable **13.4778%** recall opportunity, while **11,009** true pairs remain below review.

## Recall gap by source pair

| Source pair | True matches | Review matches | Separate matches | Auto recall | Assisted recall | Share of gap |
|---|---:|---:|---:|---:|---:|---:|
| app_users+ticketing | 42,827 | 9,403 | 7,737 | 59.9785% | 81.9343% | 72.4705% |
| social_logins+ticketing | 15,412 | 3,026 | 3,138 | 60.0052% | 79.6392% | 26.0623% |
| ticketing+ticketing | 3,010 | 208 | 134 | 88.6379% | 95.5482% | 1.4460% |
| app_users+social_logins | 16,158 | 4 | 0 | 99.9752% | 100.0000% | 0.0169% |
| app_users+store_customers | 3,496 | 1 | 0 | 99.9714% | 100.0000% | 0.0042% |
| app_users+app_users | 3,484 | 0 | 0 | 100.0000% | 100.0000% | 0.0000% |
| social_logins+social_logins | 4,671 | 0 | 0 | 100.0000% | 100.0000% | 0.0000% |
| social_logins+store_customers | 960 | 0 | 0 | 100.0000% | 100.0000% | 0.0000% |

## Largest unresolved evidence patterns

| Decision | Source pair | Evidence | Conflicts | Pairs | Mean score |
|---|---|---|---|---:|---:|
| human_review | app_users+ticketing | name_city | email_conflict | 7,912 | 0.853265 |
| human_review | social_logins+ticketing | name_city | email_conflict | 2,979 | 0.853265 |
| human_review | app_users+ticketing | exact_device_id | email_conflict | 791 | 0.687691 |
| human_review | app_users+ticketing | name_city | (none) | 631 | 0.841392 |
| human_review | ticketing+ticketing | name_city | email_conflict | 150 | 0.853265 |
| leave_separate | app_users+ticketing | exact_device_id | email_conflict;name_conflict | 7,187 | 0.287807 |
| leave_separate | social_logins+ticketing | exact_device_id | email_conflict;name_conflict | 3,079 | 0.287807 |
| leave_separate | app_users+ticketing | exact_device_id | name_conflict | 548 | 0.591836 |
| leave_separate | ticketing+ticketing | exact_device_id | email_conflict;name_conflict | 130 | 0.287807 |
| leave_separate | social_logins+ticketing | exact_device_id | name_conflict | 59 | 0.591836 |

## Score proximity

These rates are diagnostics, not proposed replacement thresholds. Moving a boundary would violate the assessment and can create false merges after transitivity.

| Score band | Pairs | Matches | Non-matches | Observed match rate |
|---|---:|---:|---:|---:|
| 0.00-0.40 | 59,424 | 10,397 | 49,027 | 17.4963% |
| 0.40-0.55 | 217 | 0 | 217 | 0.0000% |
| 0.55-0.62 (near review) | 703 | 612 | 91 | 87.0555% |
| 0.62-0.80 (review) | 953 | 857 | 96 | 89.9265% |
| 0.80-0.84 (review) | 58 | 53 | 5 | 91.3793% |
| 0.84-0.88 (near auto) | 13,317 | 11,732 | 1,585 | 88.0979% |
| 0.88-1.00 (auto) | 70,148 | 70,148 | 0 | 100.0000% |

## Evidence-backed next experiments

1. Start with **app_users+ticketing**, which contributes **72.4705%** of unresolved development/validation true pairs. Add source-aware interactions before broad global features.
2. Investigate the leading review pattern—**name_city** with **email_conflict**—using conservative name/email/address/temporal similarity. A similarity feature must require independent corroboration and must be tested against hard negatives.
3. The leading below-review pattern is **exact_device_id** with **email_conflict;name_conflict**. Do not promote shared-device evidence alone: the safe remedy is a new independent identifier or source-specific corroboration because the same pattern can describe genuinely different people on a shared device.
4. Treat the review band as the lowest-risk recall opportunity: prioritize high-yield cluster pairs for adjudication, then use double-reviewed labels in a future development set.
5. Keep Rule 2, Rule 1 and the 0.88/0.62 boundaries unchanged. Any challenger must pass zero-false-auto-merge validation, hard-negative and post-transitivity cluster gates.
6. Because validation is now being used for error analysis, confirm any future promoted model on a newly generated, untouched seed rather than repeatedly tuning against the current frozen test.

Complete aggregates are available in `recall_gap_by_source_pair.csv`, `unresolved_patterns.csv` and `score_proximity.csv`.
