# Logistic-regression MCT challenger: frozen design

**Design freeze date:** 30 August 2026  
**Validation status at design freeze:** Not read by this challenger  
**Frozen-test status at design freeze:** Not read by this challenger

## Purpose

The independent Fellegi-Sunter event model improved recall but failed the validation safety
gate because it treated correlated evidence as additive. This challenger tests whether an
interpretable logistic regression can learn those relationships while preserving zero false
automatic merges on validation.

## Dependency decision and recorded dead end

The current official scikit-learn release was installed first. Importing it failed because
Windows Application Control blocked SciPy's `_sparsetools` compiled component. The security
policy will not be bypassed. The implementation therefore uses pinned NumPy and directly
optimizes the ordinary binary logistic-loss objective with L2 regularization. This changes
the optimizer dependency, not the statistical model.

## Frozen input and feature contract

The model may read only:

- the semicolon-delimited `positive_evidence` events;
- the semicolon-delimited `conflicts` events; and
- `truth_label` during development training or validation evaluation.

It may not use the existing heuristic MCT score or decision, blocking-rule name, row or
record identifiers, hidden person identifiers, or hard-negative scenario. The 19 known
binary events and every unordered pairwise interaction are declared in
[`config/logistic_challenger.yaml`](../config/logistic_challenger.yaml). This produces 190
coefficients plus one intercept. Using every pairwise interaction is deliberately generic:
the unsafe name-and-DOB/account-conflict case did not cause a one-off feature to be added.

## Training and selection

Four L2 strengths are trained on the person-disjoint development partition only. Training
uses deterministic mini-batch Adam with a fixed row order and fixed zero initialization, so
there is no random seed or hidden stochastic choice.

Validation is then opened once to select among those four frozen candidates. A candidate is
eligible only if it creates zero false automatic merges at the unchanged 0.88 boundary.
Eligible candidates rank by auto-merge recall, assisted recall, smaller review queue, then
stronger regularization. If none passes, the logistic challenger is rejected.

The direct logistic probabilities are the candidate MCT scores. Log loss, Brier score and
equal-width calibration bins assess their probability behaviour. No post-hoc calibration
transform is fitted to validation because the same rows are already the model-selection
gate; doing both would overuse validation. The frozen test is released only after the
validation decision is saved and committed.

## Acceptance rule

The challenger replaces neither the heuristic scorer nor clustering merely because recall
increases. It must first match the heuristic's zero validation false-auto-merge result. The
assessment's fixed bands remain exact:

- `score >= 0.88`: automatic merge;
- `0.62 <= score < 0.88`: human review; and
- `score < 0.62`: leave separate.

This document and the configuration are intentionally committed before model fitting.
