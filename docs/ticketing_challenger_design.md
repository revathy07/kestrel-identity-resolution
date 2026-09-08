# Ticketing-aware logistic challenger

## Question

Can source-pair context improve the selected logistic resolver's ticketing recall without
creating any validation false auto-merges?

## Frozen design

The challenger retains the original 19 binary evidence/conflict events and 171 unordered
event interactions. It adds three main-effect contexts:

- app users + ticketing;
- social logins + ticketing; and
- ticketing + ticketing.

Every context interacts with all 19 base events, adding 57 interaction terms. The complete
design therefore contains 250 coefficients plus an intercept. No interaction was selected
individually after inspecting validation.

Source context is metadata about evidence interpretation, not a customer identifier. The
model still excludes record IDs, person IDs, blocking-rule names, hard-negative scenario,
the baseline MCT score and baseline decision from its training features.

## Reproduce

```powershell
python -m src.modeling.logistic_challenger train `
  --development-labels outputs/logistic/labelled_development_set.csv.gz `
  --output-dir outputs/ticketing-challenger `
  --config config/ticketing_challenger.yaml

python -m src.modeling.logistic_challenger validate `
  --validation-labels outputs/logistic/labelled_validation_set.csv.gz `
  --candidates outputs/ticketing-challenger/logistic_candidates.json `
  --output-dir outputs/ticketing-challenger `
  --config config/ticketing_challenger.yaml
```

## Selection contract

The candidate must:

1. produce zero validation false auto-merges;
2. exceed `v1.0` validation auto recall;
3. exceed `v1.0` validation assisted recall; and
4. keep the assessment's 0.88 and 0.62 bands unchanged.

Only development estimates coefficients. Validation chooses among the same four declared L2
strengths. A rejected candidate does not receive a deployable model artifact and is not
evaluated on the frozen test.

## Result

| Model | False auto-merges | Auto recall | Assisted recall |
|---|---:|---:|---:|
| v1.0 logistic baseline | 0 | 74.1027% | 88.0763% |
| Context L2=0.0001 | 225 | 91.2299% | 91.8531% |
| Context L2=0.001 | 131 | 86.8561% | 91.8531% |
| Context L2=0.01 | 5 | 72.7249% | 91.8006% |
| Context L2=0.1 | 0 | 43.9330% | 87.8886% |

**Decision: reject the ticketing-context challenger.**

The experiment demonstrates the privacy asymmetry clearly. Large recall gains are available
if source context is allowed to substitute for evidence, but they come with unacceptable
false merges. Strong regularization restores the observed safety result only by becoming
more conservative than the baseline.

No `logistic_model.json` exists in the challenger output by design. Rule 1, clustering and a
new-seed confirmation were not run because pair-level validation already failed the first
promotion gate.
