# Fellegi-Sunter Challenger Validation Decision

**Decision date:** 30 August 2026

**Frozen-test status at decision:** Not released for the challenger

**Decision:** Reject the raw sparse likelihood-ratio challenger as the preferred MCT model

## Validation comparison

| Metric | Heuristic MCT | Empirical FS MCT |
|---|---:|---:|
| Validation candidates | 41,057 | 41,057 |
| Auto-merges | 16,108 | 19,740 |
| True auto-merges | 16,108 | 19,739 |
| False auto-merges | 0 | 1 |
| Auto-merge precision | 100.0000% | 99.9949% |
| Auto recall within candidates | 60.4745% | 74.1065% |
| Review pairs | 4,499 | 3,952 |
| Auto-plus-review recall | 74.0276% | 87.1565% |

The challenger produces materially higher recall and a smaller review queue, but it creates
one false automatic merge. The assessment says precision on merges is the number that
matters, and the business context gives false merges a larger privacy cost than missed
matches. The heuristic baseline therefore remains preferred at this gate.

## Failure analysis

The false merge shares `name_date_of_birth` but has an `account_reference_conflict`. Its
empirical FS score is 0.959374.

The development estimates assign approximately +8.393 log2 likelihood units to name and DOB
agreement and -4.707 to account conflict. Adding them under conditional independence leaves
strong positive odds. Development contained three non-matching examples with that
combination, but all three also had a phone conflict. Their extra negative phone weight hid
the unsafe interaction during development evaluation.

This is evidence against the challenger's independence approximation, not a reason to tune
on validation. Adding the heuristic account-conflict cap after seeing this case would turn
the empirical challenger back into another manually patched rule system.

## Frozen decision

- Do not change event weights, smoothing, prior, thresholds or features after this result.
- Retain the model artifact and validation report as a genuine unsuccessful challenger.
- Release frozen-test metrics only to characterize stability, not to reverse the validation
  decision.
- Keep the heuristic MCT model as the production choice for Phase 7.
- Use the next logistic-regression challenger to model correlated evidence and interactions
  explicitly, with merge precision remaining the primary selection criterion.
