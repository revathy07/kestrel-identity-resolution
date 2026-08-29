# Heuristic versus Fellegi-Sunter MCT comparison

## Selection decision

The heuristic MCT remains selected. The decision was recorded from validation before the
challenger's frozen-test metrics were released.

## Validation gate

| Metric | Heuristic | Fellegi-Sunter |
|---|---:|---:|
| Auto-merges | 16,108 | 19,740 |
| False auto-merges | 0 | 1 |
| Auto-merge precision | 100.0000% | 99.9949% |
| Auto recall | 60.4745% | 74.1065% |
| Review pairs | 4,499 | 3,952 |
| Auto + review recall | 74.0276% | 87.1565% |

The empirical challenger improves recall but violates the higher-priority zero-false-merge
validation result. Its one failure combines name and DOB agreement with an account-reference
conflict, exposing the weakness of adding correlated likelihood evidence under an
independence approximation.

## Frozen-test characterization

| Metric | Heuristic | Fellegi-Sunter |
|---|---:|---:|
| Auto-merges | 23,824 | 29,106 |
| False auto-merges | 0 | 0 |
| Auto-merge precision | 100.0000% | 100.0000% |
| Auto recall | 60.7585% | 74.2292% |
| Review pairs | 6,490 | 5,818 |
| Auto + review recall | 74.1603% | 87.3632% |

The test result characterizes stability but cannot reverse a selection decision already made
on validation. No weights, interactions, smoothing values or thresholds were changed after
validation.

## Full population

| Decision | Heuristic | Fellegi-Sunter |
|---|---:|---:|
| Auto-merge | 81,041 | 99,247 |
| Human review | 22,263 | 19,226 |
| Leave separate | 101,243 | 86,074 |

Both models auto-merge 0/20,000 explicit hard negatives. The failed validation case was a
different non-match and demonstrates why a curated hard-negative set cannot replace general
precision measurement.

The rejected challenger is not passed to clustering. Phase 7 continues to use the selected
heuristic MCT edges. Logistic regression is the next challenger because it can estimate
correlated feature effects and interactions without manually patching this likelihood model.
