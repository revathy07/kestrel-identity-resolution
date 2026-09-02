# Project Approach

## Objective

Build a defensible identity-resolution layer across five disconnected customer systems. The
solution must prioritize false-merge prevention because an incorrect merge can expose one
customer's private orders, tickets, subscriptions or address to another person.

The assessment fixes the operational decision bands and two hard rules, but it does not
provide evidence weights. We are therefore responsible for defining, testing and documenting
how identifier evidence becomes an MCT score.

## End-to-end approach

| Stage | Approach | Result |
|---|---|---|
| Dataset | Generate controlled synthetic identities, duplicates, hard negatives and poisoned identifiers | 300,000 people and 420,000 records |
| Verification | Independently reproduce every required property | 90 passed, 0 failed, 0 warnings |
| Ingestion | Parse CSV, JSON Lines, Excel and nested social JSON without hidden truth | Five source systems loaded safely |
| Profiling | Measure missingness, uniqueness and global identifier frequency | 2,094 raw Rule 2 values found |
| Normalization | Create comparable derived identifiers while preserving raw values | 3.82 million traceable observations |
| Blocking | Create bounded plausible pairs without labels | 88.2 billion possible pairs reduced to 204,547 |
| Label design | Partition complete hidden-person relationship components | Zero person overlap across development, validation and test |
| Scoring | Compare heuristic, likelihood-ratio and logistic MCT approaches | Logistic selected on validation safety and recall |
| Clustering | Union only selected auto-merge edges and enforce Rule 1 | Logistic clusters promoted after 8/8 safety gates passed |
| Evaluation | Diagnose performance after selection using the frozen test | Source, evidence, availability, calibration and loss tables complete |

## Mandatory assessment controls

- `MCT >= 0.88`: auto-merge.
- `0.62 <= MCT < 0.88`: human review.
- `MCT < 0.62`: leave separate.
- Rule 1: reject and quarantine a complete transitive cluster containing more than 12 source
  records; never partially merge it.
- Rule 2: an attribute value occurring on more than 40 records has zero matching weight.

These controls are fixed. Individual evidence weights are not supplied by the assessment.

## MCT approach 1: explainable heuristic baseline

The first scorer positioned evidence according to expected reliability and the mandatory
thresholds:

- direct system identifiers such as account, provider and repeated record keys are strongest;
- verified email can auto-merge alone;
- ordinary email and exact phone require review alone but can auto-merge with independent
  corroboration;
- transformed email/phone evidence receives a discount;
- device, payment and demographic combinations are weaker because they may be shared; and
- explicit contradictions subtract evidence or impose safety caps.

Only the strongest feature from each correlated family contributes. Independent families
are combined with noisy-OR, and Rule 2 values contribute nothing.

This is a manually designed baseline. The exact decimal weights are documented hypotheses,
not values provided by research or the assessment.

## MCT approach 2: empirical Fellegi-Sunter challenger

To test the manual assumptions, a second scorer learned 19 event weights from the
person-disjoint development set. For event `e`:

`m(e) = P(e | true match)`

`u(e) = P(e | true non-match)`

`weight(e) = log2(m(e) / u(e))`

Jeffreys smoothing prevented infinite weights when an event had zero observed examples in
one class. Training used only `positive_evidence`, `conflicts` and the development truth
label. It did not use the heuristic score, heuristic decision, blocking rule, source-record
identity, person identity, hard-negative scenario, validation labels or test labels.

Important empirical findings included:

| Event | Development m | Development u | Interpretation |
|---|---:|---:|---|
| Exact device | 0.707142 | 0.698164 | Almost non-discriminative among candidates |
| Exact email | 0.252315 | 0.053537 | Positive evidence |
| Exact payment token | 0.015254 | 0.053537 | Negative evidence in the household-heavy candidate set |
| Name and city | 0.633889 | 0.239133 | Moderate positive evidence |
| Account conflict | 0.006901 | 0.180227 | Strong negative evidence |

## Validation comparison and decision

The model-selection decision used validation, not the frozen test:

| Validation metric | Heuristic MCT | Fellegi-Sunter MCT |
|---|---:|---:|
| Candidate pairs | 41,057 | 41,057 |
| Auto-merges | 16,108 | 19,740 |
| False auto-merges | 0 | 1 |
| Auto-merge precision | 100.0000% | 99.9949% |
| Auto recall | 60.4745% | 74.1065% |
| Human-review pairs | 4,499 | 3,952 |
| Auto + review recall | 74.0276% | 87.1565% |

The empirical model materially improved recall but produced one false automatic merge. That
pair shared name and DOB while containing an account-reference conflict. Marginal
likelihood-ratio weights treated those events as independent and overstated their combined
positive evidence.

The heuristic MCT was retained because merge precision is the primary safety metric. The
decision was committed before the empirical model's frozen-test result was released. The
empirical weights were not patched after validation.

## Frozen-test characterization

| Frozen-test metric | Heuristic MCT | Fellegi-Sunter MCT |
|---|---:|---:|
| Auto-merges | 23,824 | 29,106 |
| False auto-merges | 0 | 0 |
| Auto-merge precision | 100.0000% | 100.0000% |
| Auto recall | 60.7585% | 74.2292% |
| Human-review pairs | 6,490 | 5,818 |
| Auto + review recall | 74.1603% | 87.3632% |

The test result characterizes stability but does not reverse the validation decision. Both
models auto-merged 0/20,000 explicit hard negatives, demonstrating that curated hard
negatives do not replace general precision measurement.

## MCT approach 3: logistic-regression challenger

The third scorer directly models correlated evidence. It uses the same 19 binary evidence
and conflict events plus every unordered pairwise interaction, giving 190 coefficients and
one intercept. All interactions were declared before validation; the failed FS pair did not
cause a one-off feature to be added.

Four L2 strengths were fitted on 103,763 development pairs using deterministic mini-batch
optimization. The existing heuristic score, heuristic decision, blocking rule, record
identity, person identity and hard-negative type were excluded. The direct logistic
probability becomes the MCT score, and the required 0.88/0.62 boundaries remain unchanged.

The selected L2 strength was 0.001. Selection used validation only:

| Validation metric | Heuristic | Fellegi-Sunter | Logistic |
|---|---:|---:|---:|
| False auto-merges | 0 | 1 | 0 |
| Auto-merge precision | 100.0000% | 99.9949% | 100.0000% |
| Auto recall | 60.4745% | 74.1065% | 74.1027% |
| Human-review pairs | 4,499 | 3,952 | 4,226 |
| Auto + review recall | 74.0276% | 87.1565% | 88.0763% |

Fellegi-Sunter is excluded by the zero-false-auto-merge gate. Logistic matches the
heuristic's observed precision while materially improving both recall measures, so it is
the selected MCT. The decision was committed before the logistic frozen test was opened.

| Frozen-test metric | Heuristic | Fellegi-Sunter | Logistic |
|---|---:|---:|---:|
| False auto-merges | 0 | 0 | 0 |
| Auto-merge precision | 100.0000% | 100.0000% | 100.0000% |
| Auto recall | 60.7585% | 74.2292% | 74.2751% |
| Human-review pairs | 6,490 | 5,818 | 6,232 |
| Auto + review recall | 74.1603% | 87.3632% | 88.3834% |

Calibration is assessed with log loss, Brier score and equal-width reliability bins. No
post-hoc transform was fitted on validation because validation already selects the model.
The selected validation Brier score is 0.064285 and its ten-bin expected calibration error
is 0.013114.

## Selected production approach

The current selected path is:

1. apply Rule 2 frequency suppression;
2. generate bounded, truth-isolated candidates;
3. extract explainable agreement and conflict features;
4. apply the selected logistic MCT and exact assessment bands;
5. transitively union only auto-merge edges;
6. enforce Rule 1 on complete connected components; and
7. evaluate with hidden truth only after production outputs and hashes exist.

The rejected Fellegi-Sunter scorer was not passed into clustering. Logistic clustering was
first generated separately and compared with the preserved heuristic baseline. It was
promoted only after all eight cluster-safety gates passed.

## Business-count approach

The production-style estimator keeps hidden `person_id` and `entity_type` closed. It removes
only clusters wholly identified by observable source-specific automation behaviour or the
explicit internal-QA policy. It then calibrates unresolved score bands from the
person-disjoint frozen test and runs 500 deterministic scenarios, combining sampled links
transitively and applying Rule 1 in every simulation. These scenarios affect the aggregate
estimate only; no below-threshold link changes the operational clusters.

This produces a central candidate-resolvable estimate of **315,177** from a
traffic-excluded upper of **333,000**. The first lower sensitivity failed independent range
coverage. The corrected, general lower ceiling permits one reduction for every 33,761
canonical links still unresolved and reports **299,239–333,000**. The committed failure and
refactor are detailed in `approach_tried.md`.

## Next controlled step

Assemble Phase 14 deliverables: a concise executive memo, presentation and one-command
reproducible run guide using only the already frozen technical and business results.

Detailed failed approaches and fixes are retained in [`approach_tried.md`](approach_tried.md).
