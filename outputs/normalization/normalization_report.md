# Derived identifier-normalization report

## Executive summary

- **Source records processed:** 420,000
- **Identifier observations emitted:** 3,550,000
- **Valid observations:** 3,123,383
- **Missing observations:** 426,389
- **Invalid observations:** 228
- **Valid values changed by normalization:** 1,186,293
- **Observations carrying at least one quality flag:** 121,367
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
| ticketing | account_id | account_reference | 58,614 | 73.27% |
| store_customers | line2 | address_line2 | 46,579 | 58.22% |
| social_logins | identity_payload.verified_email | email | 51,157 | 56.84% |
| ticketing | phone | phone | 39,400 | 49.25% |
| social_logins | identity_payload.display_name | full_name | 31,322 | 34.80% |
| app_users | phone | phone | 12,210 | 10.18% |
| store_customers | contact_no | phone | 7,530 | 9.41% |
| app_users | dob | date_of_birth | 6,000 | 5.00% |

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
| app_users | last_name | last_name | trailing_quoted_annotation_removed | 2,689 |
| app_users | first_name | first_name | trailing_quoted_annotation_removed | 2,626 |
| app_users | first_name | first_name | trailing_multiline_annotation_removed | 1,968 |
| store_customers | contact_no | phone | country_code_not_explicit | 1,928 |
| store_customers | last | last_name | trailing_quoted_annotation_removed | 1,907 |
| store_customers | first | first_name | trailing_quoted_annotation_removed | 1,903 |
| app_users | last_name | last_name | trailing_multiline_annotation_removed | 1,897 |
| store_customers | line1 | address_line1 | trailing_quoted_annotation_removed | 1,847 |
| ticketing | full_name | full_name | trailing_quoted_annotation_removed | 1,777 |
| store_customers | last | last_name | trailing_multiline_annotation_removed | 1,412 |

Quality flags preserve uncertainty. A structurally valid value may still be marked as
having an unknown phone country code, an export annotation, a symbol, or an implausible DOB.
The value is not silently repaired beyond the documented transformation.

## Data lineage and reproducibility

- Normalizer version: `1`
- Configuration SHA-256: `5b12dbecc0f49286402c0093d3309db20c8a74a2c30e1bd7000596cb30aed34a`
- Normalized table SHA-256: `8f3445e1bd1c27f4b9e4c388fd1f20680bfa7343eea58781f379a1da0acaf70f`
- Compressed table size: 47,374,047 bytes
- Source fingerprints: recorded in `normalization_manifest.json`

## Boundary for the next phase

The normalized table is suitable input for candidate blocking. Before a normalized value
is allowed to create candidates or contribute evidence, the later phase must apply Rule 2
using global frequencies. This phase itself performs no matching or scoring.
