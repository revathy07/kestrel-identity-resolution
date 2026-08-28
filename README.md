# Kestrel Identity Resolution

Submission workspace for Tailwyndz Propel Lateral Drive 2026, Assessment No. 6:
building a defensible identity-matching layer across five disconnected customer systems.

## Status

| Milestone | Status |
|---|---|
| Synthetic dataset generation | Complete |
| Independent dataset verification | Complete |
| Identity profiling and Rule 2 suppression | Next |
| Candidate generation and MCT scoring | Not started |
| Capped clustering and evaluation | Not started |
| Memo and presentation | Not started |

The repository currently completes the dataset stage. It does not yet claim completion
of the downstream identity-resolution assessment.

## Repository layout

```text
data/generated/                 verified full-scale synthetic dataset
docs/                           audit evidence and development log
outputs/                        generated analysis outputs (not committed)
scripts/generate_synthetic_dataset.py
scripts/verify_synthetic_dataset.py
src/validate_generated_data.py independent compliance validator
tests/                          focused generator and validator tests
requirements.txt                pinned runtime dependency
```

See [data/README.md](data/README.md) for the role and format of every dataset file,
[docs/dataset_generator_audit.md](docs/dataset_generator_audit.md) for requirement-level
evidence, [docs/progress_log.md](docs/progress_log.md) for the development record, and
[approach_tried.md](approach_tried.md) for three measured approaches that were abandoned.

## Quick start

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Generate and audit the proportional development fixture:

```bash
python scripts/generate_synthetic_dataset.py --scale 0.01 --output-dir data/generated-small
python src/validate_generated_data.py --data-dir data/generated-small --output-dir outputs-small
```

Regenerate and audit the full dataset only when necessary:

```bash
python scripts/generate_synthetic_dataset.py --output-dir data/generated
python src/validate_generated_data.py --data-dir data/generated --output-dir outputs
```

Generation is deterministic with seed 42 unless another seed is supplied.

## Verified dataset

The committed full-scale fixture contains 300,000 invented people and 420,000 physical
rows. Independent verification reports **90 passes, 0 failures, 0 warnings, and 0
unverifiable requirements**. Important measured results include:

- 25.00% of people represented by multiple source records;
- 2.00% exact and 1.00% near duplicates;
- 8.5857% pairwise and 10.9545% canonical zero-evidence links;
- 5.7479% explicit hard negatives among 301,504 post-Rule-2 candidate pairs; and
- a 104,136-record naive poisoned component containing 78,448 hidden entities.

`person_map.csv`, `hard_negatives.json`, and the `hidden/` directory are evaluation-only
truth. They must not be used as matching features or as inputs to the production-style
resolver.

## Reproducibility

- The environment dependency is pinned in `requirements.txt`.
- The generator accepts `--seed`, `--scale`, and `--output-dir` arguments.
- Validators are read-only and return a nonzero exit status when a mandatory check fails.
- Temporary fixtures, caches, and generated validation reports are excluded from Git.

## AI usage

OpenAI Codex was used to extract and distinguish the two assessment specifications,
audit and redesign the synthetic-data generator, create the independent validators and
unit tests, diagnose failed development runs, organize the repository, and draft technical
documentation. All data and measurements were generated locally with open-source Python
libraries; no external customer dataset, paid API, or real personal information was used.
The candidate remains responsible for reviewing, explaining, and defending every submitted
design choice and threshold.
