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
- Froze the configuration before releasing the original pair-hash test and audit partitions.
- Full production result: **204,547 scored pairs**, **81,041 auto-merge edges**, **22,263
  review pairs**, and **101,243 separate decisions**.
- Historical pre-correction frozen-test result: **24,369 auto-merges at 100.0000% observed
  precision**, 61.2995% auto-merge recall and 74.7950% auto-plus-review recall. Section 12
  records why that partition design was rejected and provides the corrected result.
- No pair in the complete 20,000 explicit hard-negative manifest auto-merges.
- Phase 6 remains truth-isolated in production and forms no connected components. Rule 1's
  12-record cap is intentionally deferred to Phase 7.
- All **63 automated tests** pass.

## 11. Rule 1 capped transitive clustering

- Added deterministic union-find clustering over Phase 6 auto-merge edges only; review and
  leave-separate pairs cannot create components.
- Implemented Rule 1 after full transitive union: size 12 is accepted, size 13 or more is
  rejected and quarantined in full, with no partial merge and no threshold adjustment.
- Full run: **420,000 records**, **81,041 auto-merge edges**, **355,762 proposed/final
  components**, **48,814 merged components**, and **306,948 singletons**.
- **Zero components hit the size cap**. The largest contains six records from one hidden
  entity: one app record, one ticket record and four social-login records.
- Accepted transitive closure implies **81,863 record pairs**, all true same-entity pairs:
  **100.0000% cluster precision**, zero false merged pairs and zero mixed-person components.
- Human true-pair cluster recall is 51.5085%; lower recall is the deliberate cost of not
  silently accepting review or conflicted links.
- All **20,000 explicit hard negatives remain apart** after transitivity.
- Production assignments are truth-isolated and byte-deterministic; the row-level file is
  local while compact reports and hashes are publishable.
- All **70 automated tests** pass.

## 12. Person-disjoint labelled evaluation correction

- Audited the original stable pair-hash split before using it for an ML challenger.
- Found that **35,279/104,994 candidate endpoint people (33.6010%)** appeared in more than
  one development/test/audit partition; 22,205 affected people had positive candidate pairs.
- Preserved the pre-fix measurement in a dedicated leakage-audit report and rejected the
  pair-hash design for model comparison.
- Built an evaluation-only relationship graph using all 204,547 scored candidate edges and
  all 20,000 explicit hard-negative edges. Complete hidden-person components are assigned to
  50% development, 20% validation and 30% frozen-test hash buckets.
- The corrected split assigns all **308,400 hidden entities** across **281,183 components**;
  the largest isolation component contains 35 people.
- All **204,547 candidates are retained**, zero candidates cross partitions, and measured
  person overlap is **zero**.
- Corrected frozen-test result: **59,727 candidates**, **23,824 auto-merges at 100.0000%
  precision**, 60.7585% auto recall and 74.1603% auto-plus-review recall.
- Production scored-pair hash `9bd370fd...` is unchanged; MCT decisions and Phase 7 clusters
  were not regenerated.

## 13. Empirical Fellegi-Sunter MCT challenger

- Recorded a research-based design before implementation and retained the heuristic MCT as
  an unchanged comparison baseline.
- Estimated 19 sparse present-event log-likelihood weights from 103,763 development pairs
  only, using Jeffreys smoothing and no heuristic score, decision, record identity or
  hard-negative scenario as a predictor.
- The empirical scan found that exact device agreement was almost non-discriminative
  (`m=0.707142`, `u=0.698164`) and shared payment had negative weight in the candidate set.
- Truth-free application scored all 204,547 candidates: 99,247 auto-merge, 19,226 enter
  review and 86,074 remain separate.
- Validation increased auto recall from 60.4745% to 74.1065% but produced one false
  auto-merge, reducing precision from 100.0000% to 99.9949%.
- Rejected and committed the challenger on validation before releasing its test result.
- Frozen test later showed 74.2292% auto recall and 100.0000% precision, but did not reverse
  the pre-recorded validation decision.
- Both methods auto-merge 0/20,000 explicit hard negatives. The validation failure shows that
  curated hard negatives do not replace general precision measurement.
- The heuristic MCT remains selected; Phase 7 was not regenerated with rejected edges.
- All **73 automated tests** pass, including development-only training, deterministic
  application and validation-release isolation.

## 14. Logistic-regression MCT challenger

- Froze a 190-feature design before fitting: 19 binary evidence/conflict events and all 171
  unordered pairwise interactions, with four predeclared L2 strengths.
- The workstation's Application Control policy blocked SciPy `_sparsetools`, so the standard
  scikit-learn path was retained as a documented dead end rather than bypassing security.
  Pinned NumPy directly optimizes ordinary L2 logistic loss with deterministic mini-batch
  Adam.
- Added executable leakage boundaries: only development rows fit coefficients, only
  validation rows select regularization, and production scoring rejects labels and hidden
  person identifiers.
- Added a six-decimal threshold-parity regression after auditing raw-vs-published score
  decisions. None of the real validation candidates changed band, and selection was
  unaffected.
- Trained four candidates on **103,763 development pairs**. L2=0.001 was selected on the
  **41,057-pair validation set** with **19,738 auto-merges, zero false auto-merges, 100.0000%
  precision, 74.1027% auto recall and 88.0763% assisted recall**.
- Committed that validation decision before releasing logistic test results.
- The **59,727-pair frozen test** retained **100.0000% precision**, with 74.2751% auto recall
  and 88.3834% assisted recall. None of 20,000 explicit hard negatives auto-merged.
- Full truth-free application assigns **99,272 auto-merge**, **20,560 review** and **84,715
  leave-separate** decisions across all 204,547 candidates.
- A reproducible three-model comparison selects logistic over the heuristic because it
  preserves the zero-validation-false-merge result while improving recall. Fellegi-Sunter
  remains ineligible because of its one validation false merge.
- All **80 automated tests** passed at model selection. Cluster-level promotion followed as
  a separate controlled step.

## 15. Selected-logistic cluster promotion

- Ran the 99,272 selected logistic auto-merge edges through the unchanged Rule 1 clusterer
  in an isolated challenger directory before touching the heuristic baseline.
- Added eight executable promotion gates covering population parity, precision, false merged
  pairs, mixed-person components, transitive hard negatives, Rule 1 partial merges, accepted
  component size and human recall.
- All **8/8 gates passed**: **99,372 implied merged pairs at 100.0000% precision**, zero false
  merged pairs, zero mixed-person components and 0/20,000 hard negatives co-clustered.
- Rule 1 remained effective without intervention: zero components exceeded 12 records, zero
  records were quarantined, no partial merge occurred and the largest component was six.
- Human pairwise cluster recall improved from **51.5085% to 65.3699%**, a **13.8614
  percentage-point** increase. Recoverable canonical links accepted in one cluster increased
  from 51,576 to 64,499.
- Promoted the verified result into the standard `outputs/clustering` handoff: **342,900
  operational identities**, 57,403 merged components and 285,497 singletons.
- The former heuristic artifacts remain recoverable in Git history, and the complete compact
  comparison remains under `outputs/logistic-clustering`.
- All **83 automated tests** pass after promotion.

## 16. Consolidated Phase 12 evaluation and error analysis

- Added a post-selection evaluator that verifies hashes across the selected logistic score,
  labelled evaluation and promoted cluster artifacts before calculating diagnostics.
- Restricted source-pair, evidence, identifier-availability and error conclusions to the
  **59,727-pair person-disjoint frozen test**. Development outcomes are used only to reconcile
  the full operational decision volume.
- Frozen-test result: **29,124 auto-merges, zero observed false auto-merges, 100.0000%
  precision, 74.2751% auto recall and 88.3834% assisted recall**.
- Measured probability behaviour without refitting: Brier score **0.062639**, log loss
  **0.194626** and ten-bin expected calibration error **0.015856**.
- Located the principal false-negative concentration in ticketing-linked pairs. Auto recall
  is 59.2519% for social-logins/ticketing and 59.7687% for app-users/ticketing.
- Separated endpoint missingness from disagreement by streaming valid normalized identifier
  availability for 61,153 frozen-test endpoints.
- Attributed canonical-link losses by pipeline stage: blocking retains all **88,155/88,155
  recoverable links**, pair scoring sends 12,754 to review and 10,921 to separate, while
  transitive clustering accepts 64,499 and leaves 23,656 recoverable links unresolved.
- Grouped the 5,532 reviewed and 4,555 separated frozen-test true matches into 20 aggregate
  error patterns without exposing record or person identifiers.
- Preserved the exact MCT boundaries and selected coefficients; Phase 12 changes no model,
  calibration transform, candidate pair, decision or cluster and reports no overall accuracy.
- All **87 automated tests** pass.

## 17. Business customer-count estimate and validation refactor

- Froze an observable traffic policy before opening `entity_type`: latest dense timestamp
  window plus source-specific corroboration, with all members required for cluster removal.
- Reconciled source representation artifacts before truth release. In particular, minute-
  resolution ticket timestamps require a 68-second delay allowance for the documented
  2–8-second duplicate shift crossing a minute boundary.
- Truth-isolated classification excludes **8,400 automation clusters / 21,000 records** and
  **1,500 internal-QA clusters / records** from 342,900 operational identities, leaving a
  **333,000** marketing-safe upper.
- Calibrated unresolved edges from only the person-disjoint frozen test and ran **500**
  deterministic review-only and all-unresolved scenarios with transitive union and Rule 1.
- Central candidate-resolvable result: **315,177**; review-only median: **319,679**.
- Preserved the first frozen range (**304,896–333,000**) and its failed hidden-truth coverage
  in Git before revising the systematic lower sensitivity.
- Refactored the lower endpoint to allow one reduction for all **33,761 unresolved canonical
  links** (23,656 recoverable-not-merged plus 10,105 blocked), producing the defensible
  sensitivity range **299,239–333,000** without changing the central estimate or clusters.
- Separate truth evaluation confirms **100.0000% automation precision and recall** on this
  synthetic fixture, zero human entities removed by the automation policy, and corrected
  range coverage of the 300,000 hidden human entities.
- Quantified the **20,560 physical-pair** review queue as 685.3 hours at two minutes per pair
  or 1,713.3 hours at five minutes, explicitly marked as planning assumptions.
- All **97 automated tests** pass.

## 18. Phase 14A read-only stakeholder dashboard

- Added a locally runnable Streamlit control room with executive, technical-audit, MCT
  decision-lab and methods/limitations views.
- Restricted the data loader to a fixed allow-list of compact aggregate artifacts. It reads
  no raw source row, candidate-pair table, row-level truth, `person_map.csv` or identifier.
- Added executable reconciliation across source totals, candidate decisions, clustering
  edges, business ranges and the hidden-identifier publication flag.
- Presented the 420,000-to-315,177 count journey, 299,239–333,000 range, model comparison,
  Rule 2 blocking reduction, Rule 1 cluster safety, subgroup recall and review workload.
- Built an educational decision lab around the exact frozen logistic intercept,
  coefficients, 171 interactions and six-decimal 0.62/0.88 decision contract. It is
  explicitly read-only and warns when arbitrary feature combinations may be unsupported.
- Pinned Streamlit 1.63.0 and documented the local launch command and data boundary.
- Added five data/visual-contract tests and a four-view Streamlit smoke test. All **103
  automated tests** pass.
