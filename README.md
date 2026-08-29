# Kestrel Identity Resolution

Submission workspace for Tailwyndz Propel Lateral Drive 2026, Assessment No. 6:
building a defensible identity-matching layer across five disconnected customer systems.

## Status

| Milestone | Status |
|---|---|
| Synthetic dataset generation | Complete |
| Independent dataset verification | Complete |
| Identifier profiling and Rule 2 detection | Complete |
| Derived identifier normalization | Complete |
| Candidate blocking | Complete |
| MCT scoring and labelled pair evaluation | Complete |
| Rule 1 capped clustering and evaluation | Complete |
| Business count, memo and presentation | Next |

The repository currently completes deterministic candidate generation, explainable MCT
pair scoring, and Rule 1 capped transitive clustering. It does not yet claim completion of
the business-count recommendation or final assessment deliverables.

## Repository layout

```text
data/generated/                 verified full-scale synthetic dataset
config/schema_mapping.yaml      profiling-only canonical field mapping
docs/                           audit evidence and development log
outputs/                        compact reports; large intermediates ignored
scripts/generate_synthetic_dataset.py
scripts/verify_synthetic_dataset.py
src/ingestion/                  isolated normal-source readers
src/profiling/                  identifier profiler and Rule 2 registry
src/normalization/              derived, traceable identifier normalization
src/blocking/                   truth-isolated candidate generation
src/scoring/                    explainable pair features and MCT decisions
src/clustering/                 transitive components and Rule 1 quarantine
src/evaluation/                 post-generation synthetic-label measurement
src/validate_generated_data.py independent compliance validator
tests/                          focused generator and validator tests
requirements.txt                pinned runtime dependency
```

See [data/README.md](data/README.md) for the role and format of every dataset file,
[docs/dataset_generator_audit.md](docs/dataset_generator_audit.md) for requirement-level
evidence, [docs/progress_log.md](docs/progress_log.md) for the development record, and
[approach_tried.md](approach_tried.md) for measured approaches that were abandoned. The
complete Phase 5 implementation and verification narrative is in
[docs/phase_5_candidate_blocking_report.md](docs/phase_5_candidate_blocking_report.md).
Assumptions and their failure conditions are documented in
[assumptions.md](assumptions.md).

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

## Phase 1: identifier profiling and Rule 2

Run the isolated profiler from the repository root:

```bash
python -m src.profiling.profile_identifiers --data-dir data/generated --output-dir outputs/profiling
```

The full run profiles all 420,000 records and discovers 2,094 concept/value keys occurring
on more than 40 physical records. Those keys affect 330,000 records and account for
4,001,386,930 potential pair incidences. These are incidences, not unique pairs, because
two records can share more than one identifier.

The profiler reads only the five normal source systems. It does not require evaluation
truth, construct candidate pairs, make match decisions, perform fuzzy normalization, score
pairs, or build clusters. See [the Phase 1 report](outputs/profiling/profiling_report.md).

## Phase 4: derived normalization

Create the traceable normalized identifier table from the repository root:

```bash
python -m src.normalization.normalize_identifiers --data-dir data/generated --output-dir outputs/normalization
```

The full run emits 3,820,000 long-form identifier observations from 420,000 source records:
3,197,345 valid, 622,427 missing, and 228 structurally invalid. It changes 1,204,147 valid
derived values while leaving all raw inputs byte-identical. The 228 invalid values are
store-email fields containing export artifacts but no address; they are flagged rather than
silently repaired.

Normalization preserves email dots and plus suffixes, never infers phone country codes,
performs no fuzzy name/address comparison, and records transformations and quality flags.
See [the normalization report](outputs/normalization/normalization_report.md).

## Phase 5: candidate blocking

Generate candidates without opening any truth file:

```bash
python -m src.blocking.generate_candidates --normalized-path outputs/normalization/normalized_identifiers.csv.gz --output-dir outputs/blocking
```

The full run recalculates Rule 2 after normalization, finds 2,057 normalized concept/value
keys above 40 records, and reduces 88,199,790,000 possible unordered physical-record pairs
to 204,547 candidates (99.999768% reduction). Exact identifiers, dotted/plus email,
phone-suffix, numeric-account-reference, email-hash bridge and bounded name composites are
candidate-discovery rules only; they do not award a score or declare a match.

After generation, the separate evaluator retains all 88,155 canonical links labelled
recoverable from usable evidence (100% recoverable blocking recall). Overall, it retains
88,895 of 99,000 canonical links and discards 10,105 before scoring; 10,845 links were
deliberately labelled as having no usable exact evidence. See
[the blocking report](outputs/blocking/blocking_report.md) and
[the isolated evaluation](outputs/blocking/blocking_evaluation.md).

## Phase 6: MCT pair scoring

Score every candidate without opening evaluation labels:

```bash
python -m src.scoring.score_candidates --normalized-path outputs/normalization/normalized_identifiers.csv.gz --candidate-path outputs/blocking/candidate_pairs.csv.gz --rule2-registry outputs/blocking/normalized_rule2_registry.json --output-dir outputs/scoring
```

The scorer applies the assessment's exact bands: MCT at least 0.88 auto-merges, 0.62–0.88
enters review, and below 0.62 remains separate. The full run assigns 81,041 auto-merge
edges, 22,263 review pairs and 101,243 separate decisions. It combines only the strongest
feature in each evidence family, applies explicit conflict penalties and gives all 2,057
post-normalization Rule 2 values zero weight.

The frozen 30% test partition contains 61,206 candidates. Its 24,369 auto-merges have
100.0000% observed precision; auto-merge recall within candidates is 61.2995%, increasing
to 74.7950% when true matches sent to review are included. None of the 20,000 explicit hard
negatives auto-merge. See [the Phase 6 report](docs/phase_6_mct_scoring_report.md) and
[the frozen evaluation](outputs/scoring/mct_evaluation.md).

## Phase 7: Rule 1 capped clustering

Form transitive components from auto-merge edges only:

```bash
python -m src.clustering.cluster_records --normalized-path outputs/normalization/normalized_identifiers.csv.gz --scored-path outputs/scoring/scored_candidate_pairs.csv.gz --output-dir outputs/clustering
```

The full run forms 355,762 components: 48,814 accepted merged components and 306,948
singletons. No component exceeds Rule 1's 12-record cap; the largest contains six records
from one hidden entity. Evaluation reports 81,863 implied merged record pairs at 100.0000%
precision, zero mixed-person clusters and 0/20,000 hard negatives connected transitively.
See [the Phase 7 report](docs/phase_7_capped_clustering_report.md) and
[the cluster evaluation](outputs/clustering/cluster_evaluation.md).

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
- Temporary fixtures, caches, and large reproducible frequency tables are excluded from Git.
- The automated suite contains 70 tests, including profiling/normalization/blocking/scoring/clustering isolation,
  deterministic output and byte-level input immutability.

## AI usage

OpenAI Codex was used to extract and distinguish the two assessment specifications,
audit and redesign the synthetic-data generator, create the independent validators and
unit tests, diagnose failed development runs, organize the repository, and draft technical
documentation. All data and measurements were generated locally with open-source Python
libraries; no external customer dataset, paid API, or real personal information was used.
The candidate remains responsible for reviewing, explaining, and defending every submitted
design choice and threshold.
