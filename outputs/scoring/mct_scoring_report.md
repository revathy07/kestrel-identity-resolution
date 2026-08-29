# Phase 6 MCT scoring report

## Outcome

All **204,547** Phase 5 candidates received an explainable MCT score from 0 to 1.

| Decision | MCT band | Pairs | Percentage |
|---|---|---|---|
| auto_merge | >=0.88 | 81,041 | 39.6197% |
| human_review | >=0.62 and <0.88 | 22,263 | 10.8841% |
| leave_separate | <0.62 | 101,243 | 49.4962% |

The bands are fixed by the assessment: at least 0.88 auto-merges, 0.62–0.88 enters human review, and below 0.62 remains separate.

## Scoring method

The strongest feature in each correlated evidence family is retained. Independent family strengths are combined with noisy-OR; documented conflict penalties are then subtracted and safety caps are applied. This prevents exact email, its skeleton and its SHA-256 bridge from being counted as three independent identifiers.

## Feature coverage

| Feature | Candidate pairs |
|---|---|
| email_skeleton | 13,264 |
| exact_account_reference | 30,531 |
| exact_device_id | 143,466 |
| exact_email | 37,221 |
| exact_payment_token | 6,000 |
| exact_phone | 61,955 |
| exact_provider_id | 3,600 |
| exact_verified_email | 33,319 |
| name_city | 102,136 |
| name_date_of_birth | 4,290 |
| phone_suffix_9 | 16,630 |
| same_source_record_id | 16,800 |

## Rule 2 and isolation

The scorer loaded **2,057** normalized values occurring on more than 40 physical records. They contribute neither positive nor negative weight.
The production scorer reads no evaluation label. Pair labels are opened only by the separate Phase 6 evaluator after this output exists.

## Phase boundary

Phase 6 assigns pair decision bands but does not merge transitively or form clusters. Rule 1's 12-record cluster cap belongs to the next clustering phase.
