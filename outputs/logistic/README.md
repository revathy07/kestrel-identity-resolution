# Logistic challenger outputs

This directory contains compact, reproducible artifacts for the interpretable
logistic-regression MCT challenger.

- `logistic_candidates.json` contains the four development-trained L2 candidates.
- `logistic_coefficients.csv` presents their intercepts and 190 coefficients.
- `logistic_validation.*` records the predeclared validation-gate result.
- `logistic_model.json` exists only when a candidate passes that gate.
- `logistic_manifest.json` and `logistic_decision_summary.csv` describe truth-free scoring.
- `mct_evaluation.*` is created only after the validation decision is committed and the
  frozen test is released.

The large row-level scored and labelled gzip files are reproducible and intentionally
ignored by Git.
