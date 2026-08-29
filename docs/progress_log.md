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

The next stage after dataset generation was identifier profiling and worthless-value
detection, followed by candidate blocking, MCT scoring, capped transitive clustering,
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

## 7. Identifier profiling and Rule 2

- Added isolated readers for CSV, JSON Lines, multi-sheet Excel with a title row, and nested
  social identity payloads. Readers retain raw values and source record IDs.
- Added an explicit mapping of available and unavailable canonical concepts for every source.
- Used a disk-backed exact aggregation so no candidate pairs are materialized.
- Full seed-42 result: **420,000 records**, **17 observed identifier concepts**, and **2,094
  Rule 2 values** occurring on more than 40 physical records.
- The registry affects 330,000 records and removes **4,001,386,930 potential pair
  incidences**, leaving 1,476,529. Incidences are not unique record pairs.
- The registry naturally discovered the 40,000-record device, 4,191-record DOB,
  3,000-record phone, and 1,500- and 900-record email patterns without hard-coded values.
- All **28 tests** pass, including the strict 40/41 boundary, global cross-source counting,
  all five source formats, deterministic hashing, truth-file isolation, and byte-identical
  source files after profiling.
- Phase 1 stops before fuzzy normalization, candidate blocking, MCT scoring, matching,
  clustering, dashboards, or final evaluation.

## 8. Derived identifier normalization

- Added documented per-concept normalization rules that preserve raw values and distinguish
  valid, missing and invalid observations.
- Emails are case-folded after single-address extraction while preserving dots and plus
  suffixes. Phones lose safe display punctuation without inferred country codes.
- Names and addresses receive Unicode, case and whitespace handling only; no fuzzy
  comparison is performed. Countries map through documented ISO aliases, and DOBs are
  parsed to ISO while implausible ages remain visible as quality flags.
- A pre-Phase-5 recall audit found that optional social-login phone, device and city fields
  had been omitted from the schema map. The mapping was corrected before final blocking.
- Recognizable stacked export annotations are removed iteratively and each removal is
  quality-flagged; ordinary name tokens are not rewritten or fuzzily compared.
- The corrected full run processed **420,000 source records** and emitted **3,820,000
  identifier observations**: 3,197,345 valid, 622,427 missing and 228 invalid.
- Normalization changed 1,204,147 valid derived values and attached at least one quality
  flag to 129,727 observations.
- All five raw source fingerprints matched before and after the run. The deterministic
  compressed output is 45.2 MiB and its SHA-256 is recorded in the manifest.
- All **50 tests** pass. Phase 4 creates no pairs, fuzzy similarities, MCT scores, match
  decisions or clusters.

## 9. Candidate blocking

- Added a truth-isolated production blocker over the Phase 4 long-form table and a separate
  post-generation evaluator over hidden synthetic labels.
- Recalculated Rule 2 after normalization: **2,057 normalized concept/value keys** occur on
  more than 40 physical records and cannot create exact blocks.
- Used bounded exact and discovery-only blocks for email skeletons, email-to-SHA256 bridges,
  phone suffixes, numeric account references, and name composites. Every derived block is
  independently capped at 40 records.
- Reduced **88,199,790,000 possible unordered physical-record pairs** to **204,547 unique
  candidates**, a **99.999768% reduction**.
- Retained **88,155/88,155 canonical links labelled recoverable** (100%). Overall blocking
  retained 88,895/99,000 canonical links and discarded 10,105 before scoring.
- Retained 18,121/20,000 explicit hard-negative pairs as candidates for later scoring;
  candidate retention is not a match error because Phase 5 makes no match decisions.
- The blocker creates no MCT features or scores, match decisions, or clusters and reads no
  evaluation labels.

## 10. MCT pair scoring

- Implemented the assessment's exact MCT bands: at least 0.88 auto-merge, 0.62–0.88 human
  review, and below 0.62 leave separate.
- Added a documented noisy-OR evidence-family model so correlated email transformations are
  never double-counted, plus explicit contradiction penalties and safety caps.
- Enforced zero positive and negative contribution for all 2,057 post-normalization Rule 2
  values.
- The first development evaluation found one hard-negative false auto-merge involving a
  household email and payment token. A general household-risk cap moved that combination to
  review without changing either required threshold.
- Added a review-only floor for usable email/phone evidence with ordinary contradictions;
  account or verified-email conflicts disqualify the floor. Development auto-merge precision
  remained 100% while auto-plus-review candidate recall increased to 74.4304%.
- Froze the configuration before releasing the 30% test and 20% audit partitions.
- Full production result: **204,547 scored pairs**, **81,041 auto-merge edges**, **22,263
  review pairs**, and **101,243 separate decisions**.
- Frozen-test result: **24,369 auto-merges at 100.0000% observed precision**, 61.2995%
  auto-merge recall within candidates and 74.7950% auto-plus-review recall.
- No pair in the complete 20,000 explicit hard-negative manifest auto-merges.
- Phase 6 remains truth-isolated in production and forms no connected components. Rule 1's
  12-record cap is intentionally deferred to Phase 7.
- All **63 automated tests** pass.
