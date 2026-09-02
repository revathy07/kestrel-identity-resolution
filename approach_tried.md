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

## 6. Treating ordinary shared email and payment as independent auto-merge evidence

**What I tried.** The initial MCT formula treated ordinary exact email (0.82) and payment
token (0.55) as independent families. Their noisy-OR combination reached 0.919, above the
required 0.88 auto-merge threshold.

**Why I dropped it.** Development-only evaluation produced one false auto-merge among the
explicit hard negatives. It was the intended household case: two people shared both an
email address and payment token. Development merge precision was 99.9975%, which is not the
defensible outcome required by the problem's privacy asymmetry.

**What replaced it.** A general household-risk cap limits ordinary email plus payment alone
to 0.87, sending it to human review unless a third independent family or stronger verified
evidence exists. After regeneration, every evaluated partition had 100.0000% merge precision
on this fixture, and **0/20,000 explicit hard negatives auto-merge**. The later partition
audit changed how labelled pairs are divided, not the underlying score or this safety result.

## 7. Hashing individual candidate pairs into labelled partitions

**What I tried.** The first labelled evaluator used a stable hash of each physical candidate
pair to create 50% development, 30% frozen-test and 20% audit subsets. It retained natural
pair prevalence and kept labels out of production scoring.

**Why I dropped it.** A person-overlap audit found that **35,279 of 104,994 candidate
endpoint people (33.6010%)** appeared in multiple partitions. Among people with positive
candidate pairs, 22,205 crossed partition boundaries. This is unacceptable for an ML
challenger because records belonging to one hidden person could influence both model
development and reported holdout performance.

**What replaced it.** The corrected evaluator groups hidden people into complete
relationship components using every scored candidate and explicit hard-negative edge. Each
component is assigned once to development, validation or frozen test. The new design retains
all **204,547 candidate pairs**, assigns all **308,400 hidden entities** exactly once and has
**zero measured person overlap**. Hidden person IDs remain confined to the evaluator and are
not written to labelled artifacts.

## 8. Sparse independent Fellegi-Sunter event weights as the final MCT

**What I tried.** I estimated 19 present-event likelihood-ratio weights from the
person-disjoint development labels using Jeffreys smoothing. The frozen model ignored the
heuristic MCT score and decision, scored all 204,547 candidates and used the mandatory 0.88
and 0.62 bands unchanged.

**Why I dropped it.** Validation auto recall increased from 60.4745% to 74.1065%, but one
non-match auto-merged, reducing merge precision from 100.0000% to 99.9949%. The failed pair
shared name and DOB but had a conflicting account reference. Adding marginal likelihood
weights under an independence assumption overstated the positive evidence.

**What replaced it.** The heuristic MCT remains selected for Phase 7 because merge precision
is the primary safety measure. The empirical model and its frozen-test characterization are
retained as a genuine challenger. Logistic regression is next because it can estimate
correlated effects and interactions explicitly.

## 9. Using scikit-learn for the logistic challenger in this workstation

**What I tried.** I installed the current scikit-learn release for Python 3.14 so the next
challenger could use its standard logistic-regression implementation.

**Why I dropped it.** Importing scikit-learn failed because Windows Application Control
blocked SciPy's compiled `_sparsetools` component. This is a machine security policy, not a
modelling result, and weakening or bypassing it would make the project less reproducible and
less safe.

**What replaced it.** The challenger uses pinned NumPy to optimize the same binary logistic
loss with L2 regularization. The implementation, optimizer settings, full feature vocabulary
and generic all-pairs interaction rule are frozen in versioned files before validation is
opened. Probability quality is assessed explicitly rather than assumed from the library
name.

## 10. Evaluating raw probabilities while publishing rounded probabilities

**What I tried.** The first logistic evaluator applied the 0.88 and 0.62 bands to full
floating-point probabilities, while production scoring serialized six decimal places before
choosing a decision.

**Why I dropped it.** A value such as 0.8799996 would be review during validation but become
0.880000 and auto-merge after publication. No current validation pair changed bands this
way, but the two code paths did not express one identical contract.

**What replaced it.** Evaluation now rounds to the same six decimals before band assignment,
with a regression test for both boundaries. The four candidates were regenerated and the
same L2=0.001 validation winner remained unchanged.
