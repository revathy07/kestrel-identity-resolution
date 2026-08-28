# Kestrel Identity Resolution

Tailwyndz Propel Lateral Drive 2026 - Assessment No. 6

## Project Status

Synthetic dataset generation and independent compliance audit complete.

## Dataset generation and verification

Install the project dependencies, first run a proportional development dataset,
and execute the read-only compliance verifier:

```bash
python -m pip install -r requirements.txt
python scripts/generate_synthetic_dataset.py --scale 0.01 --output-dir data/generated-small
python src/validate_generated_data.py --data-dir data/generated-small --output-dir outputs-small
python -m unittest discover -s tests -v
```

The development run produces 3,000 people and 4,200 rows. Tests also generate and
audit an isolated temporary 1% fixture before any full regeneration.

The full 300,000-person, 420,000-row dataset has also been generated and verified:

```bash
python scripts/generate_synthetic_dataset.py --output-dir data/generated
python src/validate_generated_data.py --data-dir data/generated --output-dir outputs
```

Full-scale result: **90 mandatory passes, zero failures, zero warnings, and zero
unverifiable requirements**. Measured highlights include 25.00% multi-record people,
2.00% exact duplicates, 1.00% near duplicates, 8.5857% zero-evidence pairwise links,
10.9545% zero-evidence canonical links, and 5.7479% explicit hard negatives among
301,504 unique post-Rule-2 candidates. Naive poison matching creates a 104,136-record
component containing 78,448 distinct hidden entities.

Hidden evaluation-only metadata is written to
`data/generated/hidden/canonical_duplicate_links.jsonl`. It is never joined into normal
source-system outputs.

The validator exits with status 1 if any mandatory requirement fails. See
`docs/dataset_generator_audit.md` for the specification mapping and measured results.

## AI usage

OpenAI Codex was used to extract and distinguish the two assessment specifications,
audit and redesign the synthetic-data generator, create the independent verifier and
unit tests, diagnose failed development runs, and draft the technical documentation.
All datasets and measurements were generated locally with open-source Python libraries;
no external customer dataset, paid API, or real personal information was used. The
candidate remains responsible for reviewing, explaining, and defending every submitted
design choice and threshold.
