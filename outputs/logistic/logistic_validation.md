# Logistic challenger validation decision

**Frozen-test status:** not opened by logistic challenger

**Decision:** accept logistic candidate for frozen-test characterization

| Candidate | L2 | False auto-merges | Auto precision | Auto recall | Review pairs | Assisted recall | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| Heuristic baseline | n/a | 0 | 100.0000% | 60.4745% | 4,499 | 74.0276% | 0.108427 |
| logistic_l2_0.0001 | 0.0001 | 0 | 100.0000% | 74.0689% | 4,235 | 88.0763% | 0.063562 |
| logistic_l2_0.001 | 0.001 | 0 | 100.0000% | 74.1027% | 4,226 | 88.0763% | 0.064285 |
| logistic_l2_0.01 | 0.01 | 0 | 100.0000% | 72.3907% | 4,751 | 88.0763% | 0.069759 |
| logistic_l2_0.1 | 0.1 | 0 | 100.0000% | 47.6761% | 11,077 | 87.2015% | 0.100759 |

## Gate result

`logistic_l2_0.001` passes the zero-false-auto-merge gate and ranks first under the predeclared validation ordering. Its coefficients are frozen before the test is opened.

The mandatory 0.88/0.62 thresholds were not tuned. Validation was not used to fit a post-hoc calibration transform.
