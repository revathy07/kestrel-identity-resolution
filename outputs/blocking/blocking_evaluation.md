# Phase 5 blocking evaluation

## Main result

Blocking retained **88,895 / 99,000** canonical true links (89.7929%).
It discarded **10,105** known true links before scoring.
Among links labelled recoverable from usable evidence, it retained **88,155 / 88,155** (100.0000%).
The labels identify **10,845** zero-usable-exact-evidence links. Using only links labelled recoverable would give a 89.0455% overall baseline; discovery-only proxies can still retrieve some of the remainder.

## By evidence mode

| Mode | True links | Retained | Discarded | Recall |
|---|---|---|---|---|
| device_only | 12162 | 12162 | 0 | 100.0000% |
| email_case_variation | 4731 | 4731 | 0 | 100.0000% |
| email_dotted_local_part | 4728 | 4728 | 0 | 100.0000% |
| email_plus_suffix | 4736 | 4736 | 0 | 100.0000% |
| exact_email | 15699 | 15699 | 0 | 100.0000% |
| exact_verified_email | 20017 | 20017 | 0 | 100.0000% |
| multiple_or_other_evidence | 2458 | 2458 | 0 | 100.0000% |
| name_city_only | 11475 | 11475 | 0 | 100.0000% |
| no_usable_evidence | 10845 | 740 | 10105 | 6.8234% |
| phone_country_code | 8123 | 8123 | 0 | 100.0000% |
| phone_leading_zero | 8123 | 8123 | 0 | 100.0000% |
| phone_spaced | 4026 | 4026 | 0 | 100.0000% |

## Hard-negative candidate coverage

**18,121 / 20,000** explicit hard negatives are retained for later scoring (90.6050%). Retention here is desirable coverage, not a false match; no match decision exists yet.

## Isolation statement

This report is produced after candidate generation. Synthetic labels were used only by this evaluator and did not create, remove, score, or rank candidates.
