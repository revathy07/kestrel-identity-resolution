# Three-model MCT comparison

## Validation selection

| Model | False auto-merges | Auto precision | Auto recall | Review pairs | Assisted recall |
|---|---:|---:|---:|---:|---:|
| Heuristic MCT | 0 | 100.0000% | 60.4745% | 4,499 | 74.0276% |
| Fellegi-Sunter MCT | 1 | 99.9949% | 74.1065% | 3,952 | 87.1565% |
| Logistic-regression MCT | 0 | 100.0000% | 74.1027% | 4,226 | 88.0763% |

**Selected model:** Logistic-regression MCT

Fellegi-Sunter is ineligible because it produced one validation false auto-merge. Logistic regression matches the heuristic's zero false auto-merges while materially improving auto and assisted recall, so it wins the predeclared validation ordering.

## Frozen-test characterization

| Model | False auto-merges | Auto precision | Auto recall | Review pairs | Assisted recall |
|---|---:|---:|---:|---:|---:|
| Heuristic MCT | 0 | 100.0000% | 60.7585% | 6,490 | 74.1603% |
| Fellegi-Sunter MCT | 0 | 100.0000% | 74.2292% | 5,818 | 87.3632% |
| Logistic-regression MCT | 0 | 100.0000% | 74.2751% | 6,232 | 88.3834% |

The frozen test was released only after the logistic validation decision was committed. It characterizes stability and does not participate in model selection.

## Full-population operational effect

| Model | Auto-merge edges | Review pairs | Leave separate | Hard-negative auto-merges |
|---|---:|---:|---:|---:|
| Heuristic MCT | 81,041 | 22,263 | 101,243 | 0 |
| Fellegi-Sunter MCT | 99,247 | 19,226 | 86,074 | 0 |
| Logistic-regression MCT | 99,272 | 20,560 | 84,715 | 0 |

For the selected model, recoverable canonical-link auto recall is 73.1439% and auto-plus-review recall is 87.6116%.
