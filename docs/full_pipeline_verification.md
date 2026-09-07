# Full Pipeline Verification

## Verification result

The complete existing-data release pipeline passed on 7 September 2026. The run used the
verified scale-1 dataset in `data/generated/` and wrote isolated run artifacts outside the
OneDrive-synchronized repository.

```powershell
python scripts/run_pipeline.py --mode existing --data-dir data/generated --run-dir "$env:LOCALAPPDATA\KestrelRuns\full-existing-20260907-1904"
```

The run completed all 28 planned stages in 3,007.412 seconds. Its local audit manifest is:

```text
C:\Users\Admin\AppData\Local\KestrelRuns\full-existing-20260907-1904\pipeline_run_manifest.json
```

The manifest status is `passed`. It records each command, return code, duration and the
SHA-256 hashes of required artifacts. The location is machine-local evidence and is not a
portable repository dependency.

## Reconciled release evidence

| Gate | Verified result |
|---|---:|
| Independent scale-aware dataset checks | 66 passed, 0 failed, 0 warnings |
| Strict requirement-level dataset audit | 90 passed, 0 failed, 0 warnings, 0 unverifiable |
| Physical source records | 420,000 |
| Hidden human population used only for evaluation | 300,000 |
| Raw Rule 2 values | 2,094 |
| Potential pair incidences prevented during profiling | 4,249,099,447 |
| Candidate pairs scored | 204,547 |
| Recoverable canonical links retained by blocking | 88,155 / 88,155 (100%) |
| Intentionally unrecoverable canonical links discarded before scoring | 10,105 |
| Selected MCT model | Logistic regression, L2 = 0.001 |
| Frozen-test auto-merge precision | 100% (29,124 / 29,124) |
| Frozen-test auto recall | 74.2751% |
| Frozen-test assisted recall | 88.3834% |
| Full-population MCT decisions | 99,272 merge; 20,560 review; 84,715 separate |
| Cluster promotion checks | 8 / 8 passed |
| Rule 1 result | Applied; 0 oversized components; 0 partial merges |
| Final operational identities | 342,900 |
| Largest accepted component | 6 records |
| False merged pairs after transitivity | 0 observed |
| Recommended planning estimate | 315,177 |
| Planning range (not a confidence interval) | 299,239-333,000 |
| Hidden truth contained by planning range | Yes |
| Repository regression tests within the pipeline | 113 passed |

## Interpretation

The observed 100% precision is a result on this deterministic synthetic frozen test, not a
guarantee for unseen production data. Model selection used the person-disjoint validation
partition; the frozen test was opened only afterward. Fellegi-Sunter was not eligible for
selection because it produced one false auto-merge on validation, even though its frozen
test happened to contain no false auto-merges.

Rule 1 was executed for both the heuristic baseline and the selected logistic challenger.
No proposed component exceeded the assessment cap of 12 records, so the correct outcome
was zero quarantined components. Tests separately prove the boundary: a component of 12 is
accepted and a component of 13 is rejected in full.

The 10,105 canonical links discarded before scoring belong to the intentionally
unrecoverable group. Blocking retained every one of the 88,155 links classified as
recoverable, so those discarded links are not evidence of a blocking regression.

## Windows manifest-lock fix

The first attempt completed the 66 independent checks but OneDrive transiently locked the
manifest during atomic replacement before stage 2 began. Manifest writes now retry
transient `PermissionError` failures eight times with bounded backoff and provide an
actionable message if an external process keeps the file locked. The successful run above
also moved run artifacts outside OneDrive; no verification, scoring or safety gate was
changed.
