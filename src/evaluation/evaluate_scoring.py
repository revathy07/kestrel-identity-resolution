"""Evaluate Phase 6 MCT scores against isolated synthetic labels.

Development mode exposes only a deterministic person-disjoint development partition. Final
mode releases validation and frozen-test partitions. Nothing in this module is imported by
production scoring, and no labelled artifact contains a hidden person identifier.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


class ScoringEvaluationError(ValueError):
    """Raised when scoring evaluation inputs are missing or inconsistent."""


DECISIONS = ("auto_merge", "human_review", "leave_separate")
DEFAULT_SPLIT_RULES = Path(__file__).resolve().parents[2] / "config" / "evaluation_split.yaml"
MODEL_PARTITIONS = ("development", "validation", "test")
TEST_COLUMNS = [
    "left_source",
    "left_record_ordinal",
    "left_source_record_id",
    "right_source",
    "right_record_ordinal",
    "right_source_record_id",
    "blocking_rules",
    "positive_evidence",
    "conflicts",
    "mct_score",
    "decision",
    "truth_label",
    "hard_negative_type",
    "partition",
]


class PersonUnionFind:
    """Deterministic disjoint-set structure over hidden person identifiers."""

    def __init__(self, people: set[str]) -> None:
        self.parent = {person: person for person in people}
        self.size = {person: 1 for person in people}

    def find(self, person: str) -> str:
        if person not in self.parent:
            raise ScoringEvaluationError(f"Unknown hidden person identifier: {person!r}")
        while self.parent[person] != person:
            self.parent[person] = self.parent[self.parent[person]]
            person = self.parent[person]
        return person

    def union(self, left: str, right: str) -> str:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return left_root
        if self.size[left_root] < self.size[right_root] or (
            self.size[left_root] == self.size[right_root] and left_root > right_root
        ):
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        self.size[left_root] += self.size[right_root]
        return left_root


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_split_rules(path: Path = DEFAULT_SPLIT_RULES) -> dict[str, Any]:
    try:
        rules = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoringEvaluationError(f"Unable to load evaluation split rules from {path}: {exc}") from exc
    if not isinstance(rules, dict):
        raise ScoringEvaluationError("Evaluation split configuration must be an object")
    partitions = rules.get("partitions")
    if not isinstance(partitions, dict) or tuple(partitions) != MODEL_PARTITIONS:
        raise ScoringEvaluationError(
            f"Evaluation partitions must be ordered exactly as {MODEL_PARTITIONS}"
        )
    expected_start = 0
    for name in MODEL_PARTITIONS:
        bounds = partitions[name]
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or not all(isinstance(value, int) for value in bounds)
            or bounds[0] != expected_start
            or bounds[1] <= bounds[0]
        ):
            raise ScoringEvaluationError(f"Invalid contiguous hash range for {name}: {bounds!r}")
        expected_start = bounds[1]
    if expected_start != 100:
        raise ScoringEvaluationError("Evaluation partition hash ranges must cover 0 through 99")
    if rules.get("hash_method") != "sha256_modulo_100" or not rules.get("partition_salt"):
        raise ScoringEvaluationError("Evaluation split hash method and salt must be explicit")
    return rules


def _component_partition(members: list[str], rules: Mapping[str, Any]) -> str:
    digest = hashlib.sha256()
    digest.update(str(rules["partition_salt"]).encode("utf-8"))
    for person in sorted(members):
        encoded = person.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    bucket = int(digest.hexdigest()[:12], 16) % 100
    for name in MODEL_PARTITIONS:
        start, end = rules["partitions"][name]
        if start <= bucket < end:
            return name
    raise ScoringEvaluationError(f"No evaluation partition covers hash bucket {bucket}")


def _logical_pair(
    source_a: str, record_a: str, source_b: str, record_b: str
) -> tuple[str, str, str, str]:
    left, right = (str(source_a), str(record_a)), (str(source_b), str(record_b))
    return (*left, *right) if left <= right else (*right, *left)


def _load_truth(
    path: Path,
) -> tuple[
    dict[tuple[str, int], tuple[str, str, str]],
    dict[tuple[str, str], str],
    set[str],
]:
    counters: Counter[str] = Counter()
    truth: dict[tuple[str, int], tuple[str, str, str]] = {}
    logical_people: dict[tuple[str, str], str] = {}
    people: set[str] = set()
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"system", "record_id", "person_id", "entity_type"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ScoringEvaluationError(
                    f"Truth map is missing columns: {sorted(required - set(reader.fieldnames or []))}"
                )
            for row in reader:
                source = row["system"]
                counters[source] += 1
                record_id, person_id = row["record_id"], row["person_id"]
                truth[(source, counters[source])] = (record_id, person_id, row["entity_type"])
                logical_key = (source, record_id)
                previous = logical_people.get(logical_key)
                if previous is not None and previous != person_id:
                    raise ScoringEvaluationError(
                        f"Logical source record {logical_key} maps to multiple hidden people"
                    )
                logical_people[logical_key] = person_id
                people.add(person_id)
    except OSError as exc:
        raise ScoringEvaluationError(f"Unable to read truth map {path}: {exc}") from exc
    return truth, logical_people, people


def _load_hard_negatives(path: Path) -> tuple[dict[tuple[str, str, str, str], str], Counter[str]]:
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoringEvaluationError(f"Unable to read hard-negative labels {path}: {exc}") from exc
    if not isinstance(items, list):
        raise ScoringEvaluationError("Hard-negative labels must be a JSON list")
    pairs: dict[tuple[str, str, str, str], str] = {}
    by_type: Counter[str] = Counter()
    for item in items:
        refs = item.get("source_records", []) if isinstance(item, dict) else []
        if len(refs) != 2:
            raise ScoringEvaluationError("Every hard-negative item must identify two source records")
        pair = _logical_pair(
            refs[0]["system"], refs[0]["record_id"], refs[1]["system"], refs[1]["record_id"]
        )
        label = str(item.get("type", "unspecified"))
        pairs[pair] = label
        by_type[label] += 1
    return pairs, by_type


def _row_truth(
    row: Mapping[str, str],
    truth: Mapping[tuple[str, int], tuple[str, str, str]],
    row_number: int,
) -> tuple[tuple[str, str, str], tuple[str, str, str]]:
    try:
        left_key = (row["left_source"], int(row["left_record_ordinal"]))
        right_key = (row["right_source"], int(row["right_record_ordinal"]))
        left_truth, right_truth = truth[left_key], truth[right_key]
    except (KeyError, TypeError, ValueError) as exc:
        raise ScoringEvaluationError(f"Unable to label scored row {row_number}: {exc}") from exc
    if (
        left_truth[0] != row["left_source_record_id"]
        or right_truth[0] != row["right_source_record_id"]
    ):
        raise ScoringEvaluationError(f"Truth record ID mismatch at scored row {row_number}")
    return left_truth, right_truth


def _logical_people_for_pair(
    pair: tuple[str, str, str, str],
    logical_people: Mapping[tuple[str, str], str],
) -> tuple[str, str]:
    try:
        return logical_people[(pair[0], pair[1])], logical_people[(pair[2], pair[3])]
    except KeyError as exc:
        raise ScoringEvaluationError(f"Evaluation pair references unknown source record: {exc}") from exc


def _build_person_partitions(
    scored_path: Path,
    truth: Mapping[tuple[str, int], tuple[str, str, str]],
    logical_people: Mapping[tuple[str, str], str],
    all_people: set[str],
    hard_pairs: Mapping[tuple[str, str, str, str], str],
    split_rules: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Keep every evaluated relationship inside one person-disjoint partition."""

    union_find = PersonUnionFind(all_people)
    candidate_edges = 0
    try:
        with gzip.open(scored_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, start=1):
                left_truth, right_truth = _row_truth(row, truth, row_number)
                union_find.union(left_truth[1], right_truth[1])
                candidate_edges += 1
    except OSError as exc:
        raise ScoringEvaluationError(f"Unable to read scored pairs {scored_path}: {exc}") from exc

    for pair in hard_pairs:
        left_person, right_person = _logical_people_for_pair(pair, logical_people)
        union_find.union(left_person, right_person)

    components: dict[str, list[str]] = defaultdict(list)
    for person in sorted(all_people):
        components[union_find.find(person)].append(person)

    person_partitions: dict[str, str] = {}
    component_counts: Counter[str] = Counter()
    person_counts: Counter[str] = Counter()
    largest_component = 0
    for members in components.values():
        partition = _component_partition(members, split_rules)
        component_counts[partition] += 1
        person_counts[partition] += len(members)
        largest_component = max(largest_component, len(members))
        for person in members:
            person_partitions[person] = partition

    return person_partitions, {
        "hidden_people": len(all_people),
        "relationship_components": len(components),
        "largest_relationship_component_people": largest_component,
        "scored_candidate_edges_used": candidate_edges,
        "explicit_hard_negative_edges_used": len(hard_pairs),
        "components_by_partition": {
            name: component_counts[name] for name in MODEL_PARTITIONS
        },
        "people_by_partition": {name: person_counts[name] for name in MODEL_PARTITIONS},
    }


def _open_labelled_set(path: Path) -> tuple[Any, Any, csv.DictWriter]:
    binary = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=TEST_COLUMNS)
    writer.writeheader()
    return binary, text, writer


def _pair_metrics(counter: Counter[str]) -> dict[str, Any]:
    matches = counter["match"]
    nonmatches = counter["non_match"]
    auto_total = counter["auto_merge_match"] + counter["auto_merge_non_match"]
    review_total = counter["human_review_match"] + counter["human_review_non_match"]
    separate_total = counter["leave_separate_match"] + counter["leave_separate_non_match"]
    auto_true = counter["auto_merge_match"]
    auto_false = counter["auto_merge_non_match"]
    review_true = counter["human_review_match"]
    return {
        "candidate_pairs": matches + nonmatches,
        "true_match_pairs": matches,
        "true_non_match_pairs": nonmatches,
        "auto_merge_pairs": auto_total,
        "auto_merge_true_positives": auto_true,
        "auto_merge_false_positives": auto_false,
        "auto_merge_precision": auto_true / auto_total if auto_total else None,
        "auto_merge_recall_within_candidates": auto_true / matches if matches else None,
        "false_merge_rate": auto_false / auto_total if auto_total else None,
        "human_review_pairs": review_total,
        "human_review_true_matches": review_true,
        "human_review_yield": review_true / review_total if review_total else None,
        "leave_separate_pairs": separate_total,
        "assisted_recall_within_candidates": (auto_true + review_true) / matches if matches else None,
    }


def _canonical_metrics(counter: Counter[str]) -> dict[str, Any]:
    total = counter["total"]
    recoverable = counter["recoverable"]
    return {
        "canonical_links": total,
        "auto_merge": counter["auto_merge"],
        "human_review": counter["human_review"],
        "leave_separate": counter["leave_separate"],
        "blocked_before_scoring": counter["blocked"],
        "end_to_end_auto_merge_recall": counter["auto_merge"] / total if total else None,
        "end_to_end_assisted_recall": (counter["auto_merge"] + counter["human_review"]) / total if total else None,
        "recoverable_links": recoverable,
        "recoverable_auto_merge": counter["recoverable_auto_merge"],
        "recoverable_human_review": counter["recoverable_human_review"],
        "recoverable_leave_separate": counter["recoverable_leave_separate"],
        "recoverable_blocked": counter["recoverable_blocked"],
        "recoverable_auto_merge_recall": counter["recoverable_auto_merge"] / recoverable if recoverable else None,
        "recoverable_assisted_recall": (
            counter["recoverable_auto_merge"] + counter["recoverable_human_review"]
        ) / recoverable if recoverable else None,
    }


def _hard_negative_metrics(
    hard_pairs: Mapping[tuple[str, str, str, str], str],
    logical_scores: Mapping[tuple[str, str, str, str], tuple[float, str]],
    logical_people: Mapping[tuple[str, str], str],
    person_partitions: Mapping[str, str],
    selected_partitions: set[str],
) -> dict[str, Any]:
    overall: Counter[str] = Counter()
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    for pair, label in hard_pairs.items():
        left_person, right_person = _logical_people_for_pair(pair, logical_people)
        left_partition, right_partition = (
            person_partitions[left_person],
            person_partitions[right_person],
        )
        if left_partition != right_partition:
            raise ScoringEvaluationError("A hard-negative pair crosses person partitions")
        if left_partition not in selected_partitions:
            continue
        outcome = logical_scores.get(pair, (0.0, "blocked"))[1]
        overall[outcome] += 1
        by_type[label][outcome] += 1
    def result(counter: Counter[str]) -> dict[str, Any]:
        total = sum(counter.values())
        return {
            "pairs": total,
            "auto_merge": counter["auto_merge"],
            "human_review": counter["human_review"],
            "leave_separate": counter["leave_separate"],
            "blocked": counter["blocked"],
            "false_auto_merge_rate": counter["auto_merge"] / total if total else None,
        }
    return {
        "overall": result(overall),
        "by_type": {label: result(counter) for label, counter in sorted(by_type.items())},
    }


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4%}"


def _report(result: Mapping[str, Any]) -> str:
    partitions = result["pair_metrics_by_partition"]
    rows = []
    for name in MODEL_PARTITIONS:
        if name not in partitions:
            continue
        metrics = partitions[name]
        rows.append(
            [
                name,
                f"{metrics['candidate_pairs']:,}",
                f"{metrics['auto_merge_pairs']:,}",
                _percentage(metrics["auto_merge_precision"]),
                _percentage(metrics["auto_merge_recall_within_candidates"]),
                f"{metrics['human_review_pairs']:,}",
                _percentage(metrics["assisted_recall_within_candidates"]),
            ]
        )
    canonical = result["canonical_link_metrics"]
    hard = result["hard_negative_metrics"]["overall"]
    isolation = result["partition_isolation"]
    release_text = (
        "Development mode exposes only development metrics."
        if result["scope"] == "development"
        else "Validation mode exposes development and validation metrics while the frozen test remains locked."
        if result["scope"] == "validation"
        else "Final mode releases development, validation and frozen-test metrics."
    )
    lines = [
        "# Phase 6 MCT evaluation",
        "",
        "## Pair-level results",
        "",
        _table(
            ["Partition", "Candidates", "Auto-merges", "Merge precision", "Merge recall", "Review queue", "Auto + review recall"],
            rows,
        ),
        "",
        "Overall accuracy is intentionally not reported because obvious non-matches dominate the universe of possible pairs.",
        "",
        "## End-to-end canonical-link result",
        "",
        f"Across the released evaluation scope, **{canonical['auto_merge']:,}** canonical links auto-merge, **{canonical['human_review']:,}** enter review, **{canonical['leave_separate']:,}** remain separate after scoring, and **{canonical['blocked_before_scoring']:,}** were blocked before scoring.",
        f"End-to-end auto-merge recall is **{_percentage(canonical['end_to_end_auto_merge_recall'])}** and auto-merge-plus-review recall is **{_percentage(canonical['end_to_end_assisted_recall'])}**.",
        "",
        "## Safety result",
        "",
        f"Of **{hard['pairs']:,}** explicit hard negatives, **{hard['auto_merge']:,}** auto-merge, **{hard['human_review']:,}** enter review, **{hard['leave_separate']:,}** remain separate, and **{hard['blocked']:,}** never became candidates.",
        f"The explicit-hard-negative false auto-merge rate is **{_percentage(hard['false_auto_merge_rate'])}**.",
        "",
        "## Labelled test-set design",
        "",
        "Hidden people connected by any scored candidate or explicit hard-negative relationship are first grouped into complete isolation components. Each component is assigned by a stable salted SHA-256 hash to 50% development, 20% validation or 30% frozen-test buckets. This retains every scored candidate while preventing one person from occurring in multiple model partitions. Outcomes are not used for assignment, and person identifiers are not written to labelled artifacts.",
        "",
        "## Person-isolation proof",
        "",
        f"The split contains **{isolation['hidden_people']:,}** hidden entities in **{isolation['relationship_components']:,}** isolation components. The largest component contains **{isolation['largest_relationship_component_people']:,}** people. All **{isolation['scored_candidate_edges_used']:,}** scored candidate edges were retained, and measured person overlap across model partitions is **{isolation['person_overlap_across_model_partitions']}**.",
        "",
        "## Isolation",
        "",
        f"The MCT configuration and scored-pair file existed before labels were opened. This evaluator cannot alter production scores or decisions. {release_text}",
        "",
    ]
    return "\n".join(lines)


def evaluate_scoring(
    scored_path: Path,
    scoring_manifest_path: Path,
    truth_map_path: Path,
    canonical_links_path: Path,
    hard_negatives_path: Path,
    output_dir: Path,
    *,
    scope: str = "development",
    split_rules_path: Path = DEFAULT_SPLIT_RULES,
) -> dict[str, Any]:
    if scope not in {"development", "validation", "final"}:
        raise ScoringEvaluationError(
            "Evaluation scope must be 'development', 'validation' or 'final'"
        )
    scored_path = Path(scored_path)
    scoring_manifest_path = Path(scoring_manifest_path)
    truth_map_path = Path(truth_map_path)
    canonical_links_path = Path(canonical_links_path)
    hard_negatives_path = Path(hard_negatives_path)
    output_dir = Path(output_dir)
    split_rules_path = Path(split_rules_path)
    for path in (
        scored_path,
        scoring_manifest_path,
        truth_map_path,
        canonical_links_path,
        hard_negatives_path,
        split_rules_path,
    ):
        if not path.exists():
            raise ScoringEvaluationError(f"Required scoring-evaluation input not found: {path}")
    try:
        scoring_manifest = json.loads(scoring_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoringEvaluationError(f"Unable to read scoring manifest: {exc}") from exc
    if scoring_manifest.get("phase_boundaries", {}).get("evaluation_labels_read") is not False:
        raise ScoringEvaluationError("Scoring manifest does not prove label isolation")

    split_rules = _load_split_rules(split_rules_path)
    truth, logical_people, all_people = _load_truth(truth_map_path)
    hard_pairs, _hard_types = _load_hard_negatives(hard_negatives_path)
    person_partitions, partition_isolation = _build_person_partitions(
        scored_path,
        truth,
        logical_people,
        all_people,
        hard_pairs,
        split_rules,
    )
    selected_partitions = (
        {"development"}
        if scope == "development"
        else {"development", "validation"}
        if scope == "validation"
        else set(MODEL_PARTITIONS)
    )
    pair_counters: dict[str, Counter[str]] = defaultdict(Counter)
    false_auto_features: Counter[str] = Counter()
    false_auto_conflicts: Counter[str] = Counter()
    logical_scores: dict[tuple[str, str, str, str], tuple[float, str]] = {}
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_partitions = (
        ("development",)
        if scope == "development"
        else ("development", "validation")
        if scope == "validation"
        else MODEL_PARTITIONS
    )
    artifact_paths = {
        partition: output_dir / f"labelled_{partition}_set.csv.gz"
        for partition in artifact_partitions
    }
    artifact_handles: dict[str, tuple[Any, Any, csv.DictWriter]] = {
        partition: _open_labelled_set(path) for partition, path in artifact_paths.items()
    }
    people_seen: dict[str, set[str]] = {name: set() for name in MODEL_PARTITIONS}
    candidate_partition_counts: Counter[str] = Counter()
    try:
        with gzip.open(scored_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = set(TEST_COLUMNS) - {"truth_label", "hard_negative_type", "partition"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ScoringEvaluationError(
                    f"Scored input is missing columns: {sorted(required - set(reader.fieldnames or []))}"
                )
            for row_number, row in enumerate(reader, start=1):
                left_truth, right_truth = _row_truth(row, truth, row_number)
                label = "match" if left_truth[1] == right_truth[1] else "non_match"
                decision = row["decision"]
                if decision not in DECISIONS:
                    raise ScoringEvaluationError(f"Unknown MCT decision {decision!r} at row {row_number}")
                left_partition = person_partitions[left_truth[1]]
                right_partition = person_partitions[right_truth[1]]
                if left_partition != right_partition:
                    raise ScoringEvaluationError(
                        f"Scored candidate row {row_number} crosses person partitions"
                    )
                partition = left_partition
                candidate_partition_counts[partition] += 1
                people_seen[partition].update((left_truth[1], right_truth[1]))
                logical = _logical_pair(
                    row["left_source"], row["left_source_record_id"],
                    row["right_source"], row["right_source_record_id"],
                )
                score = float(row["mct_score"])
                previous = logical_scores.get(logical)
                if previous is None or score > previous[0]:
                    logical_scores[logical] = (score, decision)
                if partition in selected_partitions:
                    pair_counters[partition][label] += 1
                    pair_counters[partition][f"{decision}_{label}"] += 1
                    if decision == "auto_merge" and label == "non_match":
                        false_auto_features.update(filter(None, row["positive_evidence"].split(";")))
                        false_auto_conflicts.update(filter(None, row["conflicts"].split(";")))
                if partition in artifact_handles:
                    artifact_handles[partition][2].writerow(
                        {
                            **{column: row[column] for column in TEST_COLUMNS if column in row},
                            "truth_label": label,
                            "hard_negative_type": hard_pairs.get(logical, ""),
                            "partition": partition,
                        }
                    )
    finally:
        for binary, text_handle, _writer in artifact_handles.values():
            text_handle.close()
            binary.close()

    overlap = set()
    for left_index, left_name in enumerate(MODEL_PARTITIONS):
        for right_name in MODEL_PARTITIONS[left_index + 1 :]:
            overlap.update(people_seen[left_name] & people_seen[right_name])
    if overlap:
        raise ScoringEvaluationError(
            f"Person-disjoint split failed: {len(overlap)} people cross model partitions"
        )
    if sum(candidate_partition_counts.values()) != partition_isolation["scored_candidate_edges_used"]:
        raise ScoringEvaluationError("Person split did not retain every scored candidate pair")
    partition_isolation.update(
        {
            "candidate_pairs_by_partition": {
                name: candidate_partition_counts[name] for name in MODEL_PARTITIONS
            },
            "candidate_endpoint_people_by_partition": {
                name: len(people_seen[name]) for name in MODEL_PARTITIONS
            },
            "person_overlap_across_model_partitions": 0,
            "scored_candidate_pairs_crossing_partitions": 0,
            "all_scored_candidate_pairs_retained": True,
        }
    )

    canonical_counters: Counter[str] = Counter()
    try:
        with canonical_links_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    logical = _logical_pair(
                        item["source_system_a"], item["source_record_id_a"],
                        item["source_system_b"], item["source_record_id_b"],
                    )
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ScoringEvaluationError(f"Invalid canonical link at line {line_number}: {exc}") from exc
                left_person, right_person = _logical_people_for_pair(logical, logical_people)
                if left_person != right_person:
                    raise ScoringEvaluationError(
                        f"Canonical link at line {line_number} joins different hidden people"
                    )
                partition = person_partitions[left_person]
                if partition not in selected_partitions:
                    continue
                outcome = logical_scores.get(logical, (0.0, "blocked"))[1]
                canonical_counters["total"] += 1
                canonical_counters[outcome] += 1
                if bool(item.get("intended_recoverability")):
                    canonical_counters["recoverable"] += 1
                    canonical_counters[f"recoverable_{outcome}"] += 1
    except OSError as exc:
        raise ScoringEvaluationError(f"Unable to read canonical links {canonical_links_path}: {exc}") from exc

    pair_metrics = {
        partition: _pair_metrics(pair_counters[partition])
        for partition in MODEL_PARTITIONS
        if partition in selected_partitions
    }
    labelled_pair_sets: dict[str, Any] = {}
    for partition, path in artifact_paths.items():
        labelled_pair_sets[partition] = {
            "path": path.name,
            "compression": "gzip",
            "rows": pair_metrics[partition]["candidate_pairs"],
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "person_identifiers_included": False,
        }
    result: dict[str, Any] = {
        "phase": "mct_scoring_evaluation",
        "scope": scope,
        "partition_policy": {
            "method": "SHA-256 of complete hidden-person relationship component modulo 100",
            "development": "0-49 (50%)",
            "validation": "50-69 (20%)",
            "test": "70-99 (30%)",
            "component_edges": "all scored candidates plus all explicit hard negatives",
            "outcome_stratification_used": False,
            "person_disjoint": True,
            "configuration_sha256": _sha256(split_rules_path),
        },
        "scoring_configuration_sha256": scoring_manifest["inputs"]["configuration"]["sha256"],
        "scored_pairs_sha256": _sha256(scored_path),
        "pair_metrics_by_partition": pair_metrics,
        "partition_isolation": partition_isolation,
        "canonical_link_metrics": _canonical_metrics(canonical_counters),
        "hard_negative_metrics": _hard_negative_metrics(
            hard_pairs,
            logical_scores,
            logical_people,
            person_partitions,
            selected_partitions,
        ),
        "false_auto_merge_diagnostics": {
            "positive_features": dict(false_auto_features.most_common()),
            "conflicts": dict(false_auto_conflicts.most_common()),
        },
        "labelled_pair_sets": labelled_pair_sets,
        "labelled_test_set": labelled_pair_sets.get("test"),
        "isolation": {
            "scores_created_before_labels_opened": True,
            "labels_used_as_scoring_features": False,
            "hidden_people_used_only_for_evaluation_partitioning_and_labels": True,
            "person_disjoint_model_partitions": True,
            "overall_accuracy_reported": False,
            "clusters_formed": False,
        },
    }
    prefix = (
        "mct_development_evaluation"
        if scope == "development"
        else "mct_validation_evaluation"
        if scope == "validation"
        else "mct_evaluation"
    )
    (output_dir / f"{prefix}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output_dir / f"{prefix}.md").write_text(_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scored-path", type=Path, default=Path("outputs/scoring/scored_candidate_pairs.csv.gz"))
    parser.add_argument("--scoring-manifest", type=Path, default=Path("outputs/scoring/mct_manifest.json"))
    parser.add_argument("--truth-map", type=Path, default=Path("data/generated/person_map.csv"))
    parser.add_argument("--canonical-links", type=Path, default=Path("data/generated/hidden/canonical_duplicate_links.jsonl"))
    parser.add_argument("--hard-negatives", type=Path, default=Path("data/generated/hard_negatives.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/scoring"))
    parser.add_argument(
        "--scope",
        choices=("development", "validation", "final"),
        default="development",
    )
    parser.add_argument("--split-rules", type=Path, default=DEFAULT_SPLIT_RULES)
    args = parser.parse_args()
    try:
        result = evaluate_scoring(
            args.scored_path,
            args.scoring_manifest,
            args.truth_map,
            args.canonical_links,
            args.hard_negatives,
            args.output_dir,
            scope=args.scope,
            split_rules_path=args.split_rules,
        )
    except ScoringEvaluationError as exc:
        print(f"[scoring-evaluation] ERROR: {exc}")
        return 1
    development = result["pair_metrics_by_partition"].get("development")
    if development:
        precision = development["auto_merge_precision"]
        print(
            f"[scoring-evaluation] Development merge precision: "
            f"{'n/a' if precision is None else f'{precision:.4%}'}; auto-merges: {development['auto_merge_pairs']:,}"
        )
    if args.scope in {"validation", "final"}:
        validation = result["pair_metrics_by_partition"]["validation"]
        precision = validation["auto_merge_precision"]
        print(
            f"[scoring-evaluation] Validation merge precision: "
            f"{'n/a' if precision is None else f'{precision:.4%}'}; auto-merges: {validation['auto_merge_pairs']:,}"
        )
    if args.scope == "final":
        test = result["pair_metrics_by_partition"]["test"]
        precision = test["auto_merge_precision"]
        print(
            f"[scoring-evaluation] Frozen-test merge precision: "
            f"{'n/a' if precision is None else f'{precision:.4%}'}; auto-merges: {test['auto_merge_pairs']:,}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
