# Phase 5 candidate-blocking report

## Outcome

- Physical source records: **420,000**
- Unique candidate pairs: **204,547**
- Candidate reduction from all unordered pairs: **99.999768%**
- Normalized Rule 2 values (> 40 records): **2,057**
- Records with at least one eligible block: **206,489**

A candidate pair means only that two records deserve comparison. It is not a match decision.

## Blocking rules

| Rule | Eligible keys | Pair-rule incidences | Pairs unique to rule |
|---|---|---|---|
| email_sha256_bridge | 45,679 | 70,540 | 0 |
| email_skeleton | 51,761 | 83,804 | 0 |
| exact_account_reference | 22,579 | 25,531 | 0 |
| exact_device_id | 51,494 | 143,466 | 66,383 |
| exact_email | 45,679 | 70,540 | 0 |
| exact_payment_token | 5,000 | 6,000 | 0 |
| exact_phone | 38,933 | 61,955 | 0 |
| exact_provider_id | 1,800 | 3,600 | 0 |
| name_city | 60,121 | 106,346 | 30,345 |
| name_date_of_birth | 4,548 | 4,955 | 418 |
| name_postcode | 5,600 | 7,200 | 0 |
| numeric_account_reference | 27,579 | 30,531 | 0 |
| phone_suffix_9 | 46,797 | 78,585 | 16,630 |

Exact normalized values are eligible only when their normalized global frequency is 2–40.
Derived keys are discovery-only and are independently discarded when their block contains more than 40 records.
Email skeletons preserve the Phase 4 normalized value and remove dots/plus suffixes only in a temporary block key.
Phone suffixes do not infer a country code. Name composites are candidate keys, not fuzzy scores.

## Rule 2 and safety

Rule 2 was recalculated after normalization. **2,057** single concept/value keys occur on more than 40 physical records and cannot form exact blocks.
A further **10** derived keys were suppressed by the same 40-record safety cap.
The public CSV masks high-frequency values; the machine registry is an internal reproducibility artifact.

## Phase boundary

- Candidate pairs created: `true`
- Match scores calculated: `false`
- Match decisions made: `false`
- Clusters formed: `false`
- Evaluation labels read: `false`

Blocking recall and discarded true links are measured separately by the evaluation-only command.
