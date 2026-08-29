# Approaches tried and dropped

This file records approaches that were genuinely tested and then abandoned. The
measurements come from generated fixtures and independent validation, not hypothetical
examples.

## 1. Independent random allocation of records to source systems

**What I tried.** The first generator allocated people to each source independently and
relied on random sampling to reach the requested source sizes and cross-system overlaps.

**Why I dropped it.** The first 1% development run produced only **790 of the required 800
ticketing rows**. It also made important join relationships dependent on chance, so the row
counts could not be defended as a controlled property of the dataset.

**What replaced it.** I introduced a deterministic allocation plan, including controlled
repeat bookings and explicit cross-source assignments. The final generator now produces
exactly **80,000 ticketing rows and 420,000 total rows** at full scale.

## 2. Relying on naturally occurring overlap for duplicate evidence

**What I tried.** I initially generated multiple records for a person and allowed ordinary
field generation and corruption to determine whether those records still shared usable
email, phone, device, account, payment, hash, or name-and-city evidence.

**Why I dropped it.** The first measured 1% fixture left **29.59%** of true duplicate pairs
with no usable evidence. A partial revision still left **19.65%**, well above the intended
approximately 8% difficult-link rate. The result was uncontrolled and varied with the mix
of source pairs.

**What replaced it.** I assigned explicit pair-level evidence modes and measured evidence
from the emitted records. This reduced the 1% result to **8.24%** and produced a full-scale
measured rate of **10,845/126,315 = 8.5857%**.

## 3. Naive exact-value matching without frequency suppression

**What I tried.** I treated every normalized exact identifier—including default dates,
placeholder phones, shared corporate emails, and the kiosk device—as candidate evidence and
unioned matching rows transitively.

**Why I dropped it.** At full scale this created **813,387,806 unique unordered candidate
pairs**. The poison identifiers connected **104,136 records belonging to 78,448 distinct
people** into one component. This is unacceptable for a system where a false merge can
expose another customer's data.

**What replaced it.** Identifier frequencies are profiled before matching, and any value
appearing on more than 40 physical rows receives zero weight under Rule 2. Removing those
high-frequency values reduces the measured candidate set to **301,504 pairs**, only
**0.0371%** of the generator's naive unique-pair total. The completed Phase 1 profiler also
finds **2,094 high-frequency concept/value keys** across all profiled fields and calculates
that they account for **4,001,386,930 potential pair incidences**. Incidences can count the
same record pair under multiple concepts, so they are intentionally reported separately
from unique candidate pairs. The later candidate and scoring pipeline will use the registry.

The supporting measurements are recorded in
[the progress log](docs/progress_log.md),
[the dataset audit](docs/dataset_generator_audit.md), and
[the generation report](data/generated/generation_report.json).

## 4. Reusing the pre-normalization Rule 2 registry unchanged

**What I tried.** The initial plan was to feed the Phase 1 high-frequency registry directly
into blocking.

**Why I dropped it.** Phase 4 deliberately collapses safe formatting variants. Two raw keys
that were each below 41 records can therefore become one normalized value above 40. Reusing
the older counts would violate Rule 2 at the exact point candidates are created.

**What replaced it.** Phase 5 streams the final normalized table and recalculates global
physical-record frequencies before forming any block. The full run finds **2,057 normalized
Rule 2 values**; exact blocks accept frequencies 2–40 and reject 41 or more.

## 5. Accepting the first small candidate set without a recall audit

**What I tried.** The first production block rules generated **182,644 candidates**, which
looked efficient in isolation.

**Why I dropped it.** The separate canonical-link evaluation showed only **98.6614% recall
among links labelled recoverable**. It exposed two general handoff problems: optional nested
social phone/device/city identifiers had not been mapped, and stacked name export artifacts
were removed only one layer deep.

**What replaced it.** I corrected the Phase 4 mapping, made known export-annotation cleanup
iterative and quality-flagged, and reran the truth-independent blocker. The final set has
**204,547 candidates** and retains **88,155/88,155 recoverable canonical links (100%)**.
Labels remain confined to the evaluator and never become blocking features.
