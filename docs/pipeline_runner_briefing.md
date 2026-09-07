# One-command pipeline runner briefing

## Executive explanation

`scripts/run_pipeline.py` is the reproducibility entry point for the Kestrel project. It
calls the existing phase commands in their declared dependency order; it does not duplicate
or replace their logic. Every run uses a fresh isolated directory, stops on the first failed
command or missing required artifact, and writes `pipeline_run_manifest.json` with commands,
timestamps, return codes, artifact hashes and the final status.

The runner exists to answer a reviewer’s practical question: “Can somebody clone this
repository and reproduce the workflow without manually guessing the order of 20-plus
commands?”

## Commands

Install the pinned dependencies once:

```powershell
python -m pip install -r requirements.txt
```

Run the safe 10% engineering and modelling smoke test:

```powershell
python scripts/run_pipeline.py
```

This generates 42,000 records and exercises dataset verification, ingestion, profiling,
normalization, Rule 2, blocking, heuristic MCT, Fellegi–Sunter, logistic regression,
person-disjoint evaluation, transitive clustering, Rule 1 and the repository tests. On the
development machine, the frozen seed-42 smoke run completed 24 stages in 64.7 seconds. That
timing is evidence from one machine, not a performance guarantee.

Regenerate and execute the complete full-scale release in a new isolated directory:

```powershell
python scripts/run_pipeline.py --mode full
```

Reuse the committed full dataset but recalculate all downstream artifacts:

```powershell
python scripts/run_pipeline.py --mode existing --data-dir data/generated
```

Useful controls:

```powershell
python scripts/run_pipeline.py --dry-run
python scripts/run_pipeline.py --run-dir runs/my-review-run
python scripts/run_pipeline.py --skip-tests
python scripts/run_pipeline.py --help
```

`--skip-tests` saves only the final regression-suite step; it does not skip dataset,
matching or evaluation safety checks.

## Why small and full modes are different

The 10% command is a structural smoke test, not a substitute for the published full-scale
statistical result. At smaller scales:

- the strict dataset auditor’s absolute targets such as 420,000 rows and poison-cluster
  sizes are intentionally not applicable, so small mode uses the independent scale-aware
  verifier;
- development and validation partitions contain fewer examples, so the selected model or
  regularization strength can differ from the full-data result; and
- business estimates calibrated from the full frozen test must not be presented as though
  they were recalculated from a smaller sample.

Small mode therefore stops after testing all three MCT paths and the heuristic/logistic Rule
1 cluster paths. It records the small-sample model comparison as diagnostic evidence but
does not publish a new cluster promotion, consolidated stakeholder evaluation or customer
count.

Full mode and `existing` mode with a scale-1 dataset add five release steps: the strict
requirement audit, cluster-level promotion gates, consolidated frozen-test evaluation,
business estimation and hidden-truth business evaluation. The complete release also fails
if validation no longer selects the project’s declared logistic model.

## Execution order and leakage controls

| Order | Stage group | Boundary being protected |
|---:|---|---|
| 1 | Generate or validate five source systems | Hidden truth is created for evaluation, not matching |
| 2 | Profile and normalize | Raw source data remains unchanged |
| 3 | Apply Rule 2 and block candidates | Values occurring on more than 40 rows add no weight |
| 4 | Score heuristic MCT | No evaluation label is available to the scorer |
| 5 | Release development labels | Only development can estimate weights |
| 6 | Train and score Fellegi–Sunter | Frozen model scores truth-free pair features |
| 7 | Release validation labels | Validation selects models; it does not train them |
| 8 | Train, validate and score logistic candidates | Frozen test remains unreleased until selection |
| 9 | Release frozen test and compare MCT methods | Precision and recall are reported separately |
| 10 | Form transitive components | Only auto-merge edges enter clustering |
| 11 | Apply and evaluate Rule 1 | Components above 12 records are rejected in full |
| 12 | Full-scale release only: consolidate and estimate | Uncertain pairs affect aggregate sensitivity, not operational merges |
| 13 | Run repository tests | Code contracts and isolation rules are checked again |

Each subprocess receives explicit input and output paths. This prevents a stage from
silently reading a stale artifact from the repository’s normal `outputs/` directory.

## Run-directory and manifest contract

When `--run-dir` is omitted, the runner creates a UTC timestamped directory such as:

```text
runs/20260907T060000Z-small/
├── data/generated/                 # generated only in small/full modes
├── outputs/                        # phase-specific artifacts
└── pipeline_run_manifest.json      # run-level audit trail
```

The `runs/` directory is ignored by Git because its contents are reproducible and include
large row-level intermediates. The runner refuses to use a non-empty run directory and
never deletes or cleans an existing directory. This makes accidental mixing or overwriting
of evidence visible rather than convenient.

The manifest has one of three statuses:

- `running`: the command has not reached a terminal state;
- `failed`: a command returned nonzero or omitted a required artifact; or
- `passed`: every planned stage and artifact contract succeeded.

Every important emitted artifact listed in the manifest includes its SHA-256 hash. A
reviewer can therefore identify exactly which files were produced by which command.

## Verified smoke result

The final seed-42 10% run produced:

- 30,000 represented people and 42,000 physical source records;
- 66 independent scale-aware dataset checks passed, with no failures or warnings;
- 382,000 normalized identifier observations;
- 19,980 candidate pairs;
- all three MCT implementations trained, scored and evaluated;
- heuristic and logistic transitive components checked under Rule 1;
- zero false merged pairs in both 10% cluster evaluations; and
- 105 pre-existing repository tests passed during the run.

The generated smoke artifacts remain local under `runs/phase14b-smoke-final/`. Only the
runner, its tests and this briefing are committed.

## Failure behaviour and known limitation

The runner is intentionally fail-fast. It does not automatically resume or delete a failed
run. The failed manifest and already-created artifacts remain available for diagnosis; the
next attempt should use a new run directory.

An initial 1% experiment was rejected as the default smoke scale. The strict full-scale
auditor correctly flagged nine absolute-size conditions, and the small logistic sample
created three false merged pairs after transitivity. A later 10% experiment passed both
cluster evaluations but selected Fellegi–Sunter on its smaller validation partition. These
results motivated the explicit smoke-versus-release boundary; no threshold, Rule 1 gate or
precision requirement was weakened to make the runner pass.

## Mentor-ready summary

“The orchestrator is dependency-aware, path-isolated and fail-fast. It preserves our label
boundaries, runs every phase through subprocess interfaces, verifies required artifacts and
hashes them in a run manifest. Small mode proves implementation integrity without claiming
full-scale statistical reproducibility. Full mode adds the absolute dataset audit,
promotion gates, consolidated evaluation and business count, and will fail if the selected
model or cluster safety result diverges from the frozen release contract.”
