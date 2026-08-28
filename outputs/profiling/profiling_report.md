# Identifier profiling and Rule 2 report

## Executive summary

- **Total records profiled:** 420,000
- **Source counts:** app_users=120,000, store_customers=80,000, ticketing=80,000, subscriptions=50,000, social_logins=90,000
- **Identifier concepts observed:** 17
- **Rule 2 values (> 40 records):** 2,094
- **Records affected by Rule 2:** 330,000
- **Potential pair incidences prevented:** 4,001,386,930

Five most important identifier risks:

1. Unfiltered exact values imply 4,002,863,459 potential pair incidences; the same record pair may occur under several concepts.
2. Rule 2 marks 2,094 concept/value keys as worthless and removes 4,001,386,930 potential incidences.
3. 330,000 records contain at least one high-frequency value that must never carry matching weight by itself.
4. The largest high-frequency value is KIO…-1 (device_id, 40,000 records).
5. The highest missingness is store_customers.app_account_ref at 93.75%.

## Source overview

| Source | Format | Rows | Expected | Reconciled |
|---|---|---|---|---|
| app_users | csv | 120,000 | 120000 | yes |
| store_customers | csv | 80,000 | 80000 | yes |
| ticketing | jsonl | 80,000 | 80000 | yes |
| subscriptions | excel | 50,000 | 50000 | yes |
| social_logins | nested_json | 90,000 | 90000 | yes |

Only the five normal source systems were ingested. The generation report was used only to
reconcile operational row counts.

## Schema mapping

| Source | Raw field | Canonical concept | Availability |
|---|---|---|---|
| app_users | account_id | source_record_id | available (record key) |
| app_users | account_id | account_reference | available |
| app_users | email | email | available |
| app_users | phone | phone | available |
| app_users | first_name | first_name | available |
| app_users | last_name | last_name | available |
| app_users | dob | date_of_birth | available |
| app_users | device_id | device_id | available |
| app_users | city | city | available |
| app_users | country | country | available |
| app_users | — | hashed_email | unavailable |
| app_users | — | full_name | unavailable |
| app_users | — | payment_token | unavailable |
| app_users | — | address_line1 | unavailable |
| app_users | — | address_line2 | unavailable |
| app_users | — | postcode | unavailable |
| app_users | — | provider_id | unavailable |
| store_customers | customer_id | source_record_id | available (record key) |
| store_customers | app_account_ref | account_reference | available |
| store_customers | customer_email_address | email | available |
| store_customers | contact_no | phone | available |
| store_customers | first | first_name | available |
| store_customers | last | last_name | available |
| store_customers | dob | date_of_birth | available |
| store_customers | device | device_id | available |
| store_customers | line1 | address_line1 | available |
| store_customers | line2 | address_line2 | available |
| store_customers | city | city | available |
| store_customers | postcode | postcode | available |
| store_customers | country | country | available |
| store_customers | — | hashed_email | unavailable |
| store_customers | — | full_name | unavailable |
| store_customers | — | payment_token | unavailable |
| store_customers | — | provider_id | unavailable |
| ticketing | booking_id | source_record_id | available (record key) |
| ticketing | account_id | account_reference | available |
| ticketing | full_name | full_name | available |
| ticketing | email | email | available |
| ticketing | phone | phone | available |
| ticketing | device_id | device_id | available |
| ticketing | city | city | available |
| ticketing | — | hashed_email | unavailable |
| ticketing | — | first_name | unavailable |
| ticketing | — | last_name | unavailable |
| ticketing | — | date_of_birth | unavailable |
| ticketing | — | payment_token | unavailable |
| ticketing | — | address_line1 | unavailable |
| ticketing | — | address_line2 | unavailable |
| ticketing | — | postcode | unavailable |
| ticketing | — | country | unavailable |
| ticketing | — | provider_id | unavailable |
| subscriptions | subscription_id | source_record_id | available (record key) |
| subscriptions | email | email | available |
| subscriptions | subscriber_name | full_name | available |
| subscriptions | billing_name | full_name | available |
| subscriptions | payment_token | payment_token | available |
| subscriptions | country | country | available |
| subscriptions | — | hashed_email | unavailable |
| subscriptions | — | phone | unavailable |
| subscriptions | — | first_name | unavailable |
| subscriptions | — | last_name | unavailable |
| subscriptions | — | date_of_birth | unavailable |
| subscriptions | — | device_id | unavailable |
| subscriptions | — | account_reference | unavailable |
| subscriptions | — | address_line1 | unavailable |
| subscriptions | — | address_line2 | unavailable |
| subscriptions | — | city | unavailable |
| subscriptions | — | postcode | unavailable |
| subscriptions | — | provider_id | unavailable |
| social_logins | identity_payload.provider_id | source_record_id | available (record key) |
| social_logins | identity_payload.verified_email | email | available |
| social_logins | identity_payload.hashed_email | hashed_email | available |
| social_logins | identity_payload.display_name | full_name | available |
| social_logins | identity_payload.provider_id | provider_id | available |
| social_logins | — | phone | unavailable |
| social_logins | — | first_name | unavailable |
| social_logins | — | last_name | unavailable |
| social_logins | — | date_of_birth | unavailable |
| social_logins | — | device_id | unavailable |
| social_logins | — | account_reference | unavailable |
| social_logins | — | payment_token | unavailable |
| social_logins | — | address_line1 | unavailable |
| social_logins | — | address_line2 | unavailable |
| social_logins | — | city | unavailable |
| social_logins | — | postcode | unavailable |
| social_logins | — | country | unavailable |

Mappings create profiling concepts; they do not overwrite raw source fields. A concept
listed as unavailable is not manufactured from another field.

## Missingness summary

For frequency analysis, actual nulls, empty or whitespace-only strings, quoted-empty
strings, and case-insensitive `null`/`None` tokens are missing. Raw values remain unchanged.
`duplicate_value_count` means the number of distinct profiling keys occurring more than once.

| Source | Field | Concept | Missing | Missing % | Distinct | Max frequency |
|---|---|---|---|---|---|---|
| store_customers | app_account_ref | account_reference | 75,000 | 93.75% | 5,000 | 1 |
| social_logins | identity_payload.hashed_email | hashed_email | 74,375 | 82.64% | 15,625 | 1 |
| ticketing | account_id | account_reference | 58,614 | 73.27% | 21,110 | 2 |
| store_customers | line2 | address_line2 | 46,579 | 58.22% | 859 | 1,231 |
| social_logins | identity_payload.verified_email | email | 51,157 | 56.84% | 34,766 | 4 |
| ticketing | phone | phone | 39,400 | 49.25% | 40,166 | 2 |
| social_logins | identity_payload.display_name | full_name | 31,322 | 34.80% | 38,925 | 15 |
| app_users | phone | phone | 12,210 | 10.18% | 106,719 | 1,072 |
| store_customers | contact_no | phone | 7,530 | 9.41% | 70,543 | 1,928 |
| app_users | dob | date_of_birth | 6,000 | 5.00% | 22,673 | 1,517 |

Detailed metrics for every mapped field are in `column_profile.csv`.

## Identifier-frequency summary

| Concept | Distinct keys | Record incidences | Maximum frequency | Rule 2 values |
|---|---|---|---|---|
| account_reference | 122,331 | 146,386 | 3 | 0 |
| address_line1 | 22,339 | 80,000 | 17 | 0 |
| address_line2 | 859 | 33,421 | 1,231 | 217 |
| city | 26 | 280,000 | 22,259 | 26 |
| country | 20 | 250,000 | 12,686 | 20 |
| date_of_birth | 22,843 | 190,000 | 4,191 | 15 |
| device_id | 180,668 | 280,000 | 40,000 | 1 |
| email | 300,032 | 359,153 | 1,500 | 4 |
| first_name | 4,557 | 194,805 | 533 | 905 |
| full_name | 153,760 | 217,358 | 26 | 0 |
| hashed_email | 15,625 | 15,625 | 1 | 0 |
| last_name | 4,572 | 194,683 | 533 | 905 |
| payment_token | 44,500 | 50,000 | 3 | 0 |
| phone | 190,944 | 220,860 | 3,000 | 1 |
| postcode | 50,407 | 80,000 | 8 | 0 |
| provider_id | 87,300 | 90,000 | 3 | 0 |
| source_record_id | 407,400 | 420,000 | 3 | 0 |

Email keys use trim and case-fold only; dots and plus suffixes remain. Phone keys remove
safe display punctuation only; country codes are not inferred. Other concepts use trim only.
No fuzzy name or address comparison is performed.

## Rule 2 registry summary

| Concept | Masked value | Global frequency | Sources | Potential pair incidences |
|---|---|---|---|---|
| device_id | KIO…-1 | 40,000 | 2 | 799,980,000 |
| city | R*** | 22,259 | 1 | 247,720,411 |
| country | I*** | 12,686 | 3 | 80,460,955 |
| country | Uni…es | 12,667 | 3 | 80,220,111 |
| country | I** | 12,638 | 3 | 79,853,203 |
| country | U*** | 12,636 | 3 | 79,827,930 |
| country | Uni…om | 12,613 | 3 | 79,537,578 |
| country | G** | 12,556 | 3 | 78,820,290 |
| country | A** | 12,531 | 3 | 78,506,715 |
| country | A** | 12,513 | 3 | 78,281,328 |
| country | I*** | 12,502 | 3 | 78,143,751 |
| country | U** | 12,486 | 3 | 77,943,855 |
| country | I** | 12,473 | 3 | 77,781,628 |
| country | G** | 12,454 | 3 | 77,544,831 |
| country | AUS…IA | 12,446 | 3 | 77,445,235 |

The complete stakeholder-safe list is in `worthless_values.csv`. The internal
`rule2_registry.json` additionally retains the profiling key required by a later matcher.
Registry membership is discovered only from global frequencies; no known-value list is used.

## Candidate-explosion analysis

- Potential pair incidences before Rule 2: **4,002,863,459**
- Potential pair incidences removed: **4,001,386,930**
- Potential pair incidences remaining: **1,476,529**

Each value contributes `n × (n - 1) / 2`. These totals are potential pair incidences,
not unique pairs: the same two records can share more than one identifier concept. No pair
objects were constructed to calculate these figures.

## Data-quality observations

- **Missing Identifiers:** The highest missingness is store_customers.app_account_ref at 93.75%.
- **Shared Identifiers:** 330,000 records contain at least one high-frequency value that must never carry matching weight by itself.
- **Suspicious Defaults:** Frequency profiling discovered 2,094 Rule 2 values without a list of known placeholders or defaults.
- **Cross Source Schema:** Available canonical concepts by source: app_users=10, store_customers=13, ticketing=7, subscriptions=5, social_logins=5.
- **Identifier Reliability:** The concept with the most Rule 2 values is first_name (905 values).
- **Never Use Alone:** Every registry entry has zero matching weight under Rule 2 and must not be used alone.
- **Combination Only:** Names, addresses, cities, postcodes, countries, dates of birth, and other shared fields may become useful only in combination after the later scoring design is justified.

## Recommendations for later blocking and scoring

- Exclude every registry key from evidence before candidate blocking or scoring.
- Prefer surviving high-specificity identifiers for blocking; measure blocking recall later.
- Do not use names, addresses, locations, dates of birth, or shared devices alone.
- Keep raw values, profiling keys, and any later matching-normalization fields separate.
- Rebuild the registry when source volumes or schemas change; frequency is data-dependent.

This report makes no true-match decisions and implements no blocking, MCT scoring, fuzzy
matching, clustering, dashboard, or final evaluation.
