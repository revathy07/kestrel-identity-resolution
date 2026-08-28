# Approaches tried and dropped

This file records three approaches that were genuinely tested during the dataset stage and
then abandoned. The measurements come from the generated fixtures and independent
validation, not from hypothetical examples. Matching-pipeline experiments will be recorded
separately as that stage is implemented.

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
**0.0371%** of the naive total. The production-style candidate and scoring pipeline will be
built on this suppressed evidence set.

The supporting measurements are recorded in
[the progress log](docs/progress_log.md),
[the dataset audit](docs/dataset_generator_audit.md), and
[the generation report](data/generated/generation_report.json).
