# Phase 5 Candidate Blocking — Implementation and Verification Report

**Project:** Kestrel Identity Resolution  
**Assessment:** Tailwyndz Propel Lateral Drive 2026 — Assessment No. 6  
**Report date:** 29 August 2026  
**Phase status:** Complete and verified

## 1. Executive summary

Phase 5 created a deterministic candidate-generation layer over the normalized identifiers
from Phase 4. Its purpose is to avoid comparing every record with every other record while
retaining the record pairs that may represent the same person.

The full dataset contains 420,000 physical records. An exhaustive comparison would require
88,199,790,000 unordered record pairs. Phase 5 reduced this to **204,547 candidate pairs**,
a **99.999768% reduction**, while retaining **all 88,155 canonical links labelled
recoverable from usable evidence**.

Production candidate generation does not read hidden person IDs, canonical-link labels,
hard-negative labels, evidence-mode labels, or scenario metadata. Synthetic labels are
opened only afterward by a separate evaluator. Phase 5 does not calculate MCT scores,
declare matches, or form identity clusters.

## 2. Work completed before candidate generation

Before implementing blocking, the Phase 4 handoff was audited for completeness. Counts,
source coverage, raw-file hashes, normalization statuses, and phase boundaries were checked.
The audit found two omissions that would have reduced candidate recall.

### 2.1 Optional social identifiers were missing from the schema map

Linked social-login payloads can contain nested phone, device and city identifiers. These
fields were present in the raw data but were not included in the original canonical schema
mapping. The mapping was corrected to include:

- `identity_payload.phone` as `phone`;
- `identity_payload.device_id` as `device_id`; and
- `identity_payload.city` as `city`.

The corrected normalization run produced **3,820,000 identifier observations**:

| Normalization status | Observations |
|---|---:|
| Valid | 3,197,345 |
| Missing | 622,427 |
| Invalid | 228 |
| **Total** | **3,820,000** |

All raw source fingerprints remained unchanged.

### 2.2 Stacked name-export annotations were only partly removed

Some synthetic dirty names contained more than one appended export artifact, for example a
quoted note, an emoji and a trailing multilingual greeting. The earlier normalizer removed
only the final visible artifact. Removing it could expose another artifact behind it.

The cleanup was changed to remove recognized trailing export annotations iteratively. Every
removal remains traceable through a quality flag. This is deterministic data cleaning; it
does not rewrite name tokens, calculate name similarity, or perform fuzzy matching. Tests
also verify that an ordinary name containing the word `Hello` is not truncated.

## 3. Why candidate blocking was necessary

Scoring all 88.2 billion possible pairs would be computationally wasteful and would expose
the later resolver to enormous numbers of obviously unrelated records. At the same time,
using every shared value for blocking is unsafe. Placeholder phones, default dates,
corporate emails and shared devices can create huge poisoned blocks.

Candidate blocking therefore serves two purposes:

1. reduce the comparison space to a practical size; and
2. retain likely same-person pairs without treating common identifiers as evidence.

A candidate means only that a pair should be evaluated later. It is not a match.

## 4. Rule 2 implementation

Rule 2 states that a single attribute value occurring on more than 40 physical records has
zero matching weight. Phase 5 recalculates this frequency from the final normalized values
instead of reusing the earlier raw-profile registry. This is necessary because normalization
can collapse multiple formatting variants into one value whose combined frequency exceeds
40.

The strict boundary is implemented as follows:

- frequency 1: cannot create a pair;
- frequencies 2–40: eligible for an exact block; and
- frequency 41 or higher: excluded under Rule 2.

The full normalized run identified **2,057 high-frequency concept/value keys**. The masked
registry can be reviewed without exposing full identifier values. Derived discovery keys
are also independently capped at 40 records, even when their individual components are not
used as exact evidence.

## 5. Candidate-discovery rules

The following deterministic rules were implemented:

| Rule | Purpose | Important limitation |
|---|---|---|
| Exact email | Find records with the same normalized email | Suppressed above 40 records |
| Exact hashed email | Link identical validated SHA-256 values | Does not reverse a hash |
| Exact phone | Find identical normalized phones | No country code is inferred |
| Exact device ID | Find records sharing a device | High-frequency devices are suppressed |
| Exact account reference | Link explicit account references | Exact normalized value only |
| Exact payment token | Retain shared-payment candidates | Candidate evidence only at this phase |
| Exact provider ID | Detect repeated provider identities | Does not imply cross-provider equivalence |
| Email skeleton | Discover dotted-local-part and plus-suffix variants | Temporary block key only; stored email is unchanged |
| Email SHA-256 bridge | Compare a normalized clear email hash with a supplied hash | Assumes documented SHA-256 representation |
| Phone suffix 9 | Discover safe formatting/country-prefix variants | Does not award a phone match score |
| Numeric account reference | Reconcile zero-padded numeric references | Applied only to digit-only references |
| Name + city | Recover name-and-city-only cases | Composite block capped at 40 |
| Name + date of birth | Provide an additional conservative name block | Candidate-only; not a match rule |
| Name + postcode | Provide an additional conservative name block | Candidate-only; not a match rule |

No hard-coded poison value, source record pair, hidden person ID, evidence-mode label, or
ground-truth scenario is used by these rules.

## 6. Production implementation

The blocker performs three streaming passes over the compressed normalized table:

1. count normalized concept/value frequencies globally;
2. size exact and derived blocks and build the post-normalization Rule 2 registry; and
3. materialize eligible block memberships and deduplicate unordered candidate pairs.

Physical record identity uses source, source row ordinal and source record ID. Candidate
pairs are written deterministically with every blocking rule that discovered each pair. A
temporary local SQLite database performs pair/rule deduplication and is deleted when the run
finishes.

The production manifest explicitly records these phase boundaries:

| Operation | Performed in Phase 5 production blocking? |
|---|---|
| Candidate pairs created | Yes |
| Evaluation labels read | No |
| Match scores calculated | No |
| Match decisions made | No |
| Clusters formed | No |

## 7. Full-scale production result

| Metric | Result |
|---|---:|
| Physical records | 420,000 |
| All possible unordered pairs | 88,199,790,000 |
| Eligible block keys | 407,570 |
| Candidate pair-rule incidences before pair deduplication | 693,053 |
| Unique candidate pairs | 204,547 |
| Candidates as percentage of all pairs | 0.000231913% |
| Candidate-space reduction | 99.999768087% |
| Normalized Rule 2 values | 2,057 |
| Oversized derived blocks suppressed | 10 |
| Records with at least one eligible block | 206,489 |

The compressed candidate file is deterministic and its SHA-256 is recorded in the
manifest. It is kept as a reproducible local intermediate rather than committed to Git.

## 8. Isolated blocking evaluation

After candidate generation completed, a separate evaluator loaded the synthetic canonical
links and hard-negative manifest. It did not modify or regenerate candidates.

### 8.1 Canonical-link recall

| Metric | Result |
|---|---:|
| Canonical true links | 99,000 |
| Retained as candidates | 88,895 |
| Discarded before scoring | 10,105 |
| Overall blocking recall | 89.7929% |
| Links labelled recoverable | 88,155 |
| Recoverable links retained | 88,155 |
| Recoverable links discarded | 0 |
| **Recoverable blocking recall** | **100.0000%** |

The dataset labels 10,845 links as having no usable exact evidence. Candidate-only proxies
still discover 740 of them, leaving 10,105 discarded. Recovering such a pair as a candidate
does not mean it is a match; it only means a later scorer will examine it.

All labelled recoverable evidence modes achieved 100% candidate recall, including exact and
verified email, email case/dot/plus variants, phone country/spacing/leading-zero variants,
device-only, name-and-city-only, and multiple/other evidence.

### 8.2 Hard-negative coverage

The blocker retained **18,121 of 20,000 explicit hard-negative pairs (90.6050%)** for later
scoring. This is useful: the scoring phase needs to see difficult non-match pairs in order to
test whether its evidence weighting and thresholds reject them. Candidate retention is not
a false-positive match because no match decision has been made.

## 9. Verification performed

The completed implementation passed the following checks:

- **50 automated tests passed** with no failures;
- strict Rule 2 boundary tests prove that 40 is eligible and 41 is excluded;
- candidate output is byte-for-byte deterministic on repeated fixtures;
- candidate rows are unique, ordered and traceable to physical source records;
- production blocking runs without truth files and contains no references to truth-file or
  truth-field names;
- evaluation labels are used only after candidate generation;
- all raw source hashes remain unchanged;
- public Rule 2 output contains masked values rather than normalized direct values;
- large candidate and internal registry files remain excluded from Git; and
- the independent dataset compliance audit still reports **90 passed, 0 failed, 0 warnings,
  and 0 unverifiable requirements**.

## 10. Files created or changed

### Production configuration and code

- `config/blocking_rules.yaml`
- `src/blocking/rules.py`
- `src/blocking/generate_candidates.py`

### Evaluation and tests

- `src/evaluation/evaluate_blocking.py`
- `tests/test_blocking.py`
- updated normalization tests for newly covered fields and stacked artifacts

### Compact reports

- `outputs/blocking/candidate_manifest.json`
- `outputs/blocking/blocking_rule_summary.csv`
- `outputs/blocking/normalized_rule2_values.csv`
- `outputs/blocking/blocking_report.md`
- `outputs/blocking/blocking_evaluation.json`
- `outputs/blocking/blocking_evaluation.md`

### Documentation and repository policy

- updated the main README and progress log;
- documented attempted approaches and why the first candidate set was rejected;
- documented generated-output publication policy; and
- updated `.gitignore` so compact evidence is publishable while reproducible row-level and
  unmasked artifacts remain local.

## 11. Limitations and interpretation

- The 100% result is blocking recall over this deterministic synthetic dataset, not proof of
  perfect recall on future real customer data.
- Candidate rules intentionally trade some additional comparisons for recall. The later MCT
  scorer must still reject weak and conflicting pairs.
- The email-hash bridge depends on the documented normalized SHA-256 representation.
- Phone suffix and name composite agreement must not be interpreted as standalone match
  decisions.
- Rule 2 and the 40-record derived-block cap must remain in force during later feature and
  score generation.
- Hidden synthetic labels are suitable for development evaluation but must remain isolated
  from production matching inputs.

## 12. Handoff to the next phase

Phase 5 supplies a bounded, traceable candidate set for Phase 6. The next phase should:

1. calculate pairwise comparison features only for these candidates;
2. assign documented MCT evidence weights while keeping every Rule 2 value at zero weight;
3. preserve per-feature explanations for each score;
4. select thresholds using a development set without contaminating the final labelled test
   set; and
5. stop before transitive clustering until pairwise score behaviour and hard-negative errors
   are understood.

Phase 5 is therefore complete, but the overall identity-resolution assessment is not yet
complete. MCT scoring, threshold selection, capped clustering, final evaluation, the memo and
the presentation remain to be implemented.
