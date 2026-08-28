# Progress log

This log records actual development work and measured outcomes. It is not a substitute for
Git history; use small terminal commits with messages explaining each change and why.

## 1. Specification review

- Separated the dataset-generation brief from the downstream identity-resolution
  assessment instructions.
- Audited the original generator and found uncontrolled identity counts, unsafe CSV
  duplicate mutation, missing join/orphan logic, manifest-only hard negatives, and
  hard-coded report values.
- Added an independent, read-only verifier and focused unit tests.

## 2. Controlled generator redesign

- Replaced random person sampling with a deterministic allocation plan.
- Added the `--scale` and `--output-dir` arguments for reproducible development runs.
- Added structured duplicate generation, row-complete ground truth, bot entity types,
  source-backed hard negatives, controlled poison identifiers, conditional missingness,
  mixed timestamp semantics, shuffled sources, and measured reporting.

## 3. Development-scale iterations

The 1% fixture used 3,000 people and 4,200 rows.

- First run exposed a ticket allocation shortfall: 790 rows were produced instead of 800.
  The planner was corrected to create controlled repeat bookings.
- Initial pair measurement found 29.59% zero-evidence pairs, then 19.65%. A source-pair
  breakdown showed unintended ticket/social gaps. Rich linked-provider evidence reduced the
  measured value to 8.24%.
- The shared-ID check initially failed because store records had no genuine app reference.
  The allocation was changed so 50 development-scale people occur in both systems with the
  app integer ID represented as a zero-padded store reference.
- Orphan event IDs progressed from 0%, to 2.90%, to the valid 3.86% range after selection
  was based only on ticket rows capable of exposing an account reference.
- Shuffling revealed that near-duplicate verification was order-dependent (1.33%). Counting
  distinct content variants per record ID fixed the observed rate to exactly 1.00%.
- Final development result: **66 PASS, 0 FAIL, 0 WARN**. The focused test suite has
  since expanded to 15 passing tests.

## 4. Full-scale run

The default generator produced exactly 420,000 rows:

| Source | Rows |
|---|---:|
| app_users | 120,000 |
| store_customers | 80,000 |
| ticketing | 80,000 |
| subscriptions | 50,000 |
| social_logins | 90,000 |

Measured full-scale results:

- 300,000 distinct invented people; 25.00% have multiple records; 500 have six or more.
- 8,400 exact duplicates (2.00%) and 4,200 near duplicates (1.00%).
- 10,845 of 126,315 true pairs have zero usable evidence (8.5857%).
- 931 of 21,386 nonblank ticket account IDs are orphans (4.35%).
- 21,000 bot rows (5.00%), 1,500 QA rows, and 2,550 late events (3.19%).
- Poison counts: 3,000 placeholder phones, 4,191 default DOBs, 900 corporate-email rows,
  40,000 kiosk-device rows, and 1,500 staff-test emails.
- The largest single poison frequency is 40,000, while naive transitive union expands that
  connected poisoned component to 104,136 rows and 78,448 hidden entities; the independent
  verifier reproduces it.
- Final independent compliance result: **90 PASS, 0 FAIL, 0 WARN, 0 NOT VERIFIABLE**.

## 5. Next engineering stage

The next stage is the assessment solution, not more data generation: identifier profiling,
worthless-value detection, candidate blocking, MCT scoring, capped transitive clustering,
labelled evaluation, and the required written deliverables.

## 6. Rigorous audit corrections

- Separated nested social provider identity payloads from outer event metadata; Twitter now
  has provider-ID/display-name-only payloads and Apple has hashed-email-only payloads.
- Replaced obvious automation domains/names/IDs with neutral synthetic values while retaining
  three independently measured behavioural signals.
- Prevented null-like, quoted-empty and artifact-only emails from creating matcher edges.
- Added `total_row_count` and exact record/person poison-component metrics to the report.
- Added 99,000 hidden canonical star links with evidence-mode and recoverability metadata.
- Replaced incidence-based hard-negative scoring with explicitly labelled pairs over unique
  unordered post-Rule-2 candidates; full-scale result is 17,330/301,504 (5.7479%).
- Final independent audit: **90 PASS, 0 FAIL, 0 WARN, 0 NOT VERIFIABLE**.
