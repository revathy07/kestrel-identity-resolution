# Logistic challenger validation decision

**Frozen-test status:** not opened by logistic challenger

**Decision:** reject logistic challenger

| Candidate | L2 | False auto-merges | Auto precision | Auto recall | Review pairs | Assisted recall | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| v1.0 logistic baseline | n/a | 0 | 100.0000% | 74.1027% | 4,226 | 88.0763% | 0.064285 |
| logistic_l2_0.0001 | 0.0001 | 225 | 99.0826% | 91.2299% | 185 | 91.8531% | 0.035087 |
| logistic_l2_0.001 | 0.001 | 131 | 99.4369% | 86.8561% | 1,458 | 91.8531% | 0.036252 |
| logistic_l2_0.01 | 0.01 | 5 | 99.9742% | 72.7249% | 5,366 | 91.8006% | 0.044278 |
| logistic_l2_0.1 | 0.1 | 0 | 100.0000% | 43.9330% | 11,936 | 87.8886% | 0.084991 |

## Gate result

No candidate passes every configured validation promotion gate; the challenger is rejected.

The mandatory 0.88/0.62 thresholds were not tuned. Validation was not used to fit a post-hoc calibration transform.
