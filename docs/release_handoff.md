# Technical Release Handoff

## Release scope

This repository is the complete technical identity-resolution release through dataset
generation, independent verification, ingestion, profiling, normalization, Rule 2,
blocking, three MCT approaches, validation-based model selection, Rule 1 clustering,
frozen-test evaluation, business estimation, dashboarding and reproducible orchestration.

The client memo and presentation are intentionally deferred and are not represented as
complete in this technical release.

## Prerequisites

- Git;
- Python 3.11 or newer;
- enough local storage for the 137.7 MB committed dataset, the Python environment and run
  artifacts (the verified full run produced 252.7 MB); and
- approximately 50 minutes for the existing-data full release on the development machine,
  with actual time dependent on hardware.

Reserve at least 1 GB of free working space. Run artifacts should be placed outside a
OneDrive, Dropbox or similar synchronized directory when possible.

## Windows PowerShell clean setup

```powershell
git clone https://github.com/revathy07/kestrel-identity-resolution.git
Set-Location kestrel-identity-resolution
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Calling the virtual-environment Python directly avoids activation and executable-PATH
problems.

## Reproduction choices

| Goal | Command mode | What it proves |
|---|---|---|
| Quick engineering check | `small` | Generates 10% data and exercises all three MCT methods and both Rule 1 paths |
| Exact release reproduction | `existing` | Reuses the committed verified scale-1 dataset and executes all 28 release stages |
| Everything from seed 42 | `full` | Regenerates scale-1 data and executes the complete release |

Recommended exact release reproduction on Windows:

```powershell
$runDir = Join-Path $env:LOCALAPPDATA ("KestrelRuns\full-existing-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
.\.venv\Scripts\python.exe scripts/run_pipeline.py --mode existing --data-dir data/generated --run-dir $runDir
```

Every attempt must use a fresh run directory. The runner never deletes or overwrites an
existing non-empty run.

## Acceptance result

A successful exact release ends with `PIPELINE PASSED` and should reproduce:

- 66 independent dataset checks passed;
- 90 strict requirements passed;
- 420,000 records and 204,547 candidate pairs;
- logistic regression with L2 `0.001` selected on validation;
- 8/8 cluster promotion gates passed;
- 342,900 operational identities and zero observed false merged pairs;
- recommended planning estimate 315,177 and planning range 299,239-333,000; and
- 113 repository tests passed.

The run-level `pipeline_run_manifest.json` is the authoritative orchestration receipt. It
records command order, status, duration, return code and SHA-256 hashes for required
artifacts. See [full pipeline verification](full_pipeline_verification.md) for the verified
reference run and interpretation limits.

## Continuous integration

`.github/workflows/tests.yml` runs two mandatory jobs on every push and pull request:

1. all repository unit, integration and dashboard smoke tests; and
2. the isolated 10% end-to-end pipeline, with compact evidence retained for seven days.

The scale-1 release is intentionally not run on every commit because it takes about 50
minutes. A maintainer can open **Actions -> Continuous integration -> Run workflow**, enable
**Run the 28-stage release**, and start the manually gated full verification. Compact
release evidence is retained for fourteen days.

## Clean-clone verification

The hand-off procedure was independently exercised on 7 September 2026 from committed
revision `f63b5e1` in a new checkout outside the OneDrive workspace. A new virtual
environment installed only `requirements.txt`, all 113 tests passed, and the existing-data
`--dry-run` resolved the expected 28-stage release plan. No uncommitted source file,
pre-existing virtual environment or repository `runs/` artifact was needed.

## Reviewer checklist

- Confirm the checkout is at the intended release tag or commit.
- Confirm dependency installation succeeds in a new virtual environment.
- Confirm all 113 tests pass.
- Use `--dry-run` if command order needs review before execution.
- Use a fresh, non-synchronized `--run-dir`.
- Treat 100% observed synthetic precision as test evidence, not as a production guarantee.
- Verify `pipeline_run_manifest.json` has status `passed` before accepting derived reports.
