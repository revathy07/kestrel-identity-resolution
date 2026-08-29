# Derived identifier-normalization report

## Executive summary

- **Source records processed:** 420,000
- **Identifier observations emitted:** 3,820,000
- **Valid observations:** 3,197,345
- **Missing observations:** 622,427
- **Invalid observations:** 228
- **Valid values changed by normalization:** 1,204,147
- **Observations carrying at least one quality flag:** 129,727
- **Raw source files modified:** no; before/after SHA-256 fingerprints match

The output is a derived, long-form identifier table. It contains no candidate pairs,
pair similarities, MCT scores, match decisions, clusters, or evaluation labels.

## Normalization principles

- Preserve every raw source value.
- Represent missing, invalid and valid values separately.
- Do not infer missing phone country codes.
- Preserve email dots and plus suffixes.
- Do not apply fuzzy name or address logic.
- Do not use evaluation truth or scenario labels.

## Concept strategies

| Canonical concept | Strategy |
|---|---|
| account_reference | identifier |
| address_line1 | address |
| address_line2 | address |
| city | city |
| country | country |
| date_of_birth | date_of_birth |
| device_id | identifier |
| email | email |
| first_name | name |
| full_name | name |
| hashed_email | sha256_hash |
| last_name | name |
| payment_token | identifier |
| phone | phone |
| postcode | postcode |
| provider_id | identifier |
| source_record_id | identifier |

Email dots and plus suffixes remain intact. Phones lose only safe display punctuation;
a missing country code is never inferred. Names and addresses use Unicode, case and
whitespace handling only—no fuzzy comparison is performed. Country aliases map to ISO
two-letter codes. DOB parsing emits ISO dates and flags implausible ages without repairing them.

## Highest missingness

| Source | Field | Concept | Missing | Missing % |
|---|---|---|---|---|
| store_customers | app_account_ref | account_reference | 75,000 | 93.75% |
| social_logins | identity_payload.hashed_email | hashed_email | 74,375 | 82.64% |
| social_logins | identity_payload.city | city | 67,000 | 74.44% |
| social_logins | identity_payload.device_id | device_id | 67,000 | 74.44% |
| ticketing | account_id | account_reference | 58,614 | 73.27% |
| social_logins | identity_payload.phone | phone | 61,512 | 68.35% |
| store_customers | line2 | address_line2 | 46,996 | 58.74% |
| social_logins | identity_payload.verified_email | email | 51,157 | 56.84% |
| ticketing | phone | phone | 39,400 | 49.25% |
| social_logins | identity_payload.display_name | full_name | 31,322 | 34.80% |

## Invalid-value summary

| Source | Field | Concept | Invalid | Invalid % |
|---|---|---|---|---|
| store_customers | customer_email_address | email | 228 | 0.28% |

## Quality flags

| Source | Field | Concept | Flag | Observations |
|---|---|---|---|---|
| ticketing | full_name | full_name | contains_digit | 34,408 |
| social_logins | identity_payload.display_name | full_name | contains_digit | 31,178 |
| ticketing | phone | phone | country_code_not_explicit | 12,149 |
| store_customers | customer_email_address | email | email_extracted_from_export_text | 4,656 |
| subscriptions | email | email | email_extracted_from_export_text | 3,062 |
| app_users | last_name | last_name | trailing_quoted_annotation_removed | 2,761 |
| app_users | first_name | first_name | trailing_quoted_annotation_removed | 2,681 |
| app_users | first_name | first_name | trailing_multiline_annotation_removed | 1,968 |
| store_customers | first | first_name | trailing_quoted_annotation_removed | 1,953 |
| store_customers | last | last_name | trailing_quoted_annotation_removed | 1,942 |
| store_customers | contact_no | phone | country_code_not_explicit | 1,928 |
| app_users | last_name | last_name | trailing_multiline_annotation_removed | 1,897 |
| store_customers | line1 | address_line1 | trailing_quoted_annotation_removed | 1,889 |
| ticketing | full_name | full_name | trailing_quoted_annotation_removed | 1,829 |
| app_users | last_name | last_name | trailing_multilingual_greeting_removed | 1,540 |

Quality flags preserve uncertainty. A structurally valid value may still be marked as
having an unknown phone country code, an export annotation, a symbol, or an implausible DOB.
The value is not silently repaired beyond the documented transformation.

## Data lineage and reproducibility

- Normalizer version: `1`
- Configuration SHA-256: `d570498324466868c0c4b2db4e0d021d5d008780a59b2432eab94acb0eba71e2`
- Normalized table SHA-256: `b7b0ce1b2fefee13dffbf2b7d80fc3769cdf337ffa6b33ee9c6baee6f2975c54`
- Compressed table size: 49,463,456 bytes
- Source fingerprints: recorded in `normalization_manifest.json`

## Boundary for the next phase

The normalized table is suitable input for candidate blocking. Before a normalized value
is allowed to create candidates or contribute evidence, the later phase must apply Rule 2
using global frequencies. This phase itself performs no matching or scoring.
