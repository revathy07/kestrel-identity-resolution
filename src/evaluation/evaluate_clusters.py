"""Evaluate accepted and quarantined Phase 7 components against isolated labels.

This evaluator runs after production clustering. It reports pairwise cluster precision and
recall, canonical-link outcomes, transitive hard-negative safety, purity and the truth-level
contents of quarantined components without emitting person identifiers.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from src.evaluation.evaluate_scoring import _load_hard_negatives, _load_truth, _logical_pair


class ClusterEvaluationError(ValueError):
    """Raised when cluster evaluation inputs are missing or inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pairs(count: int) -> int:
    return math.comb(count, 2) if count >= 2 else 0


def _same_component(
    pair: tuple[str, str, str, str], mapping: Mapping[tuple[str, str], set[str]]
) -> bool:
    left = mapping.get((pair[0], pair[1]), set())
    right = mapping.get((pair[2], pair[3]), set())
    return bool(left & right)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4%}"


def _report(result: Mapping[str, Any]) -> str:
    pairwise = result["pairwise_cluster_metrics"]
    canonical = result["canonical_link_metrics"]
    hard = result["hard_negative_metrics"]
    quarantine = result["quarantine_evaluation"]
    return "\n".join(
        [
            "# Phase 7 cluster evaluation",
            "",
            "## Merge safety",
            "",
            f"Accepted components imply **{pairwise['predicted_merged_pairs']:,}** merged record pairs. **{pairwise['true_positive_merged_pairs']:,}** are true same-entity pairs and **{pairwise['false_positive_merged_pairs']:,}** are false merges.",
            f"Pairwise cluster precision is **{_percentage(pairwise['precision'])}**. Pairwise recall across all hidden same-entity record pairs is **{_percentage(pairwise['recall_all_entities'])}**; human-record recall is **{_percentage(pairwise['recall_humans'])}**.",
            "",
            "## Cluster purity",
            "",
            f"Accepted merged components: **{result['accepted_cluster_purity']['accepted_merged_components']:,}**; mixed-person accepted components: **{result['accepted_cluster_purity']['mixed_person_components']:,}**; largest number of hidden entities in one accepted component: **{result['accepted_cluster_purity']['maximum_hidden_entities_in_component']:,}**.",
            "",
            "## Canonical-link outcomes",
            "",
            _table(
                ["Outcome", "Links"],
                [[key.replace("_", " "), f"{value:,}"] for key, value in canonical.items() if key.endswith("links")],
            ),
            "",
            "## Hard-negative transitivity",
            "",
            f"Of **{hard['explicit_hard_negative_pairs']:,}** explicit hard negatives, **{hard['co_clustered_after_transitivity']:,}** end in one accepted cluster, **{hard['co_quarantined_in_one_oversized_component']:,}** occur together only in quarantine, and **{hard['kept_apart']:,}** remain apart.",
            "",
            "## Rule 1 quarantine contents",
            "",
            f"Rule 1 quarantined **{quarantine['component_count']:,}** components containing **{quarantine['record_count']:,}** records and **{quarantine['distinct_hidden_entities']:,}** distinct hidden entities in aggregate.",
            (
                f"The largest quarantined component contains {quarantine['largest_component']['source_record_count']:,} records, {quarantine['largest_component']['distinct_hidden_entities']:,} hidden entities and source composition `{json.dumps(quarantine['largest_component']['source_counts'], sort_keys=True)}`."
                if quarantine["largest_component"]
                else "No component exceeded the cap, so the quarantine is empty."
            ),
            "",
            "## Interpretation",
            "",
            "Overall accuracy is intentionally omitted. Cluster precision is the primary safety metric because one false edge can contaminate an entire transitive component. Automated entities remain in the operational count; removing bots or QA traffic requires a separately validated policy rather than hidden labels.",
            "",
        ]
    )


def evaluate_clusters(
    assignments_path: Path,
    clustering_manifest_path: Path,
    truth_map_path: Path,
    canonical_links_path: Path,
    hard_negatives_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    assignments_path = Path(assignments_path)
    clustering_manifest_path = Path(clustering_manifest_path)
    truth_map_path = Path(truth_map_path)
    canonical_links_path = Path(canonical_links_path)
    hard_negatives_path = Path(hard_negatives_path)
    output_dir = Path(output_dir)
    for path in (
        assignments_path,
        clustering_manifest_path,
        truth_map_path,
        canonical_links_path,
        hard_negatives_path,
    ):
        if not path.exists():
            raise ClusterEvaluationError(f"Required cluster-evaluation input not found: {path}")
    try:
        manifest = json.loads(clustering_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClusterEvaluationError(f"Unable to read clustering manifest: {exc}") from exc
    if manifest.get("phase_boundaries", {}).get("evaluation_labels_read") is not False:
        raise ClusterEvaluationError("Clustering manifest does not prove label isolation")
    if manifest.get("phase_boundaries", {}).get("oversized_components_partially_merged") is not False:
        raise ClusterEvaluationError("Clustering manifest does not prove full oversized rejection")

    truth = _load_truth(truth_map_path)
    person_types: dict[str, str] = {}
    total_person_counts: Counter[str] = Counter()
    for _key, (_record_id, person_id, entity_type) in truth.items():
        total_person_counts[person_id] += 1
        person_types[person_id] = entity_type

    accepted_people: dict[str, Counter[str]] = defaultdict(Counter)
    accepted_types: dict[str, Counter[str]] = defaultdict(Counter)
    quarantine_people: dict[str, Counter[str]] = defaultdict(Counter)
    quarantine_types: dict[str, Counter[str]] = defaultdict(Counter)
    quarantine_sources: dict[str, Counter[str]] = defaultdict(Counter)
    logical_final: dict[tuple[str, str], set[str]] = defaultdict(set)
    logical_proposed_quarantine: dict[tuple[str, str], set[str]] = defaultdict(set)
    assignment_count = 0
    try:
        with gzip.open(assignments_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {
                "source",
                "record_ordinal",
                "source_record_id",
                "proposed_component_id",
                "proposed_component_size",
                "final_cluster_id",
                "cluster_status",
            }
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ClusterEvaluationError(
                    f"Assignment input is missing columns: {sorted(required - set(reader.fieldnames or []))}"
                )
            for row_number, row in enumerate(reader, start=1):
                try:
                    key = (row["source"], int(row["record_ordinal"]))
                    record_id, person_id, entity_type = truth[key]
                    size = int(row["proposed_component_size"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ClusterEvaluationError(f"Unable to label assignment row {row_number}: {exc}") from exc
                if record_id != row["source_record_id"]:
                    raise ClusterEvaluationError(f"Truth record ID mismatch at assignment row {row_number}")
                logical = (row["source"], record_id)
                status = row["cluster_status"]
                final_id = row["final_cluster_id"]
                proposed_id = row["proposed_component_id"]
                if status == "quarantined_oversized":
                    if final_id or size <= 12:
                        raise ClusterEvaluationError("A quarantined component was partially accepted or not oversized")
                    quarantine_people[proposed_id][person_id] += 1
                    quarantine_types[proposed_id][entity_type] += 1
                    quarantine_sources[proposed_id][row["source"]] += 1
                    logical_proposed_quarantine[logical].add(proposed_id)
                elif status in {"accepted_singleton", "accepted_merged"}:
                    if not final_id or size > 12:
                        raise ClusterEvaluationError("An accepted assignment violates Rule 1")
                    accepted_people[final_id][person_id] += 1
                    accepted_types[final_id][entity_type] += 1
                    logical_final[logical].add(final_id)
                else:
                    raise ClusterEvaluationError(f"Unknown cluster status {status!r}")
                assignment_count += 1
    except OSError as exc:
        raise ClusterEvaluationError(f"Unable to read cluster assignments {assignments_path}: {exc}") from exc
    if assignment_count != int(manifest["total_source_records"]):
        raise ClusterEvaluationError("Assignment row count does not match clustering manifest")

    predicted_pairs = true_positive_pairs = human_true_positive_pairs = 0
    mixed_clusters = 0
    maximum_entities = 0
    accepted_merged_components = 0
    for cluster_id, counts in accepted_people.items():
        del cluster_id
        size = sum(counts.values())
        if size > 1:
            accepted_merged_components += 1
        predicted_pairs += _pairs(size)
        true_positive_pairs += sum(_pairs(count) for count in counts.values())
        human_true_positive_pairs += sum(
            _pairs(count) for person_id, count in counts.items() if person_types[person_id] == "human"
        )
        distinct = len(counts)
        mixed_clusters += int(distinct > 1)
        maximum_entities = max(maximum_entities, distinct)
    false_positive_pairs = predicted_pairs - true_positive_pairs
    total_true_pairs = sum(_pairs(count) for count in total_person_counts.values())
    total_human_true_pairs = sum(
        _pairs(count) for person_id, count in total_person_counts.items() if person_types[person_id] == "human"
    )

    canonical_counts: Counter[str] = Counter()
    try:
        with canonical_links_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    pair = _logical_pair(
                        item["source_system_a"], item["source_record_id_a"],
                        item["source_system_b"], item["source_record_id_b"],
                    )
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ClusterEvaluationError(f"Invalid canonical link at line {line_number}: {exc}") from exc
                if _same_component(pair, logical_final):
                    outcome = "accepted_cluster"
                elif _same_component(pair, logical_proposed_quarantine):
                    outcome = "quarantined_together"
                else:
                    outcome = "not_merged"
                canonical_counts[outcome] += 1
                if bool(item.get("intended_recoverability")):
                    canonical_counts[f"recoverable_{outcome}"] += 1
    except OSError as exc:
        raise ClusterEvaluationError(f"Unable to read canonical links {canonical_links_path}: {exc}") from exc

    hard_pairs, _types = _load_hard_negatives(hard_negatives_path)
    hard_counts: Counter[str] = Counter()
    hard_by_type: dict[str, Counter[str]] = defaultdict(Counter)
    for pair, label in hard_pairs.items():
        if _same_component(pair, logical_final):
            outcome = "co_clustered"
        elif _same_component(pair, logical_proposed_quarantine):
            outcome = "co_quarantined"
        else:
            outcome = "kept_apart"
        hard_counts[outcome] += 1
        hard_by_type[label][outcome] += 1

    quarantine_rows: list[dict[str, Any]] = []
    for component_id, counts in quarantine_people.items():
        quarantine_rows.append(
            {
                "proposed_component_id": component_id,
                "source_record_count": sum(counts.values()),
                "distinct_hidden_entities": len(counts),
                "maximum_records_for_one_hidden_entity": max(counts.values()),
                "entity_type_counts": dict(sorted(quarantine_types[component_id].items())),
                "source_counts": dict(sorted(quarantine_sources[component_id].items())),
            }
        )
    quarantine_rows.sort(key=lambda row: (-row["source_record_count"], row["proposed_component_id"]))
    distinct_quarantined_entities = len(
        {person_id for counts in quarantine_people.values() for person_id in counts}
    )
    result: dict[str, Any] = {
        "phase": "capped_cluster_evaluation",
        "assignment_rows": assignment_count,
        "pairwise_cluster_metrics": {
            "predicted_merged_pairs": predicted_pairs,
            "true_positive_merged_pairs": true_positive_pairs,
            "false_positive_merged_pairs": false_positive_pairs,
            "precision": true_positive_pairs / predicted_pairs if predicted_pairs else None,
            "all_hidden_true_pairs": total_true_pairs,
            "recall_all_entities": true_positive_pairs / total_true_pairs if total_true_pairs else None,
            "human_hidden_true_pairs": total_human_true_pairs,
            "human_true_positive_merged_pairs": human_true_positive_pairs,
            "recall_humans": human_true_positive_pairs / total_human_true_pairs if total_human_true_pairs else None,
        },
        "accepted_cluster_purity": {
            "accepted_components": len(accepted_people),
            "accepted_merged_components": accepted_merged_components,
            "mixed_person_components": mixed_clusters,
            "maximum_hidden_entities_in_component": maximum_entities,
        },
        "canonical_link_metrics": {
            "total_links": sum(canonical_counts[key] for key in ("accepted_cluster", "quarantined_together", "not_merged")),
            "accepted_cluster_links": canonical_counts["accepted_cluster"],
            "quarantined_together_links": canonical_counts["quarantined_together"],
            "not_merged_links": canonical_counts["not_merged"],
            "recoverable_accepted_cluster_links": canonical_counts["recoverable_accepted_cluster"],
            "recoverable_quarantined_together_links": canonical_counts["recoverable_quarantined_together"],
            "recoverable_not_merged_links": canonical_counts["recoverable_not_merged"],
        },
        "hard_negative_metrics": {
            "explicit_hard_negative_pairs": len(hard_pairs),
            "co_clustered_after_transitivity": hard_counts["co_clustered"],
            "co_quarantined_in_one_oversized_component": hard_counts["co_quarantined"],
            "kept_apart": hard_counts["kept_apart"],
            "by_type": {
                label: {
                    "co_clustered": counts["co_clustered"],
                    "co_quarantined": counts["co_quarantined"],
                    "kept_apart": counts["kept_apart"],
                }
                for label, counts in sorted(hard_by_type.items())
            },
        },
        "quarantine_evaluation": {
            "component_count": len(quarantine_rows),
            "record_count": sum(row["source_record_count"] for row in quarantine_rows),
            "distinct_hidden_entities": distinct_quarantined_entities,
            "largest_component": quarantine_rows[0] if quarantine_rows else None,
            "components": quarantine_rows,
        },
        "entity_count_context": {
            "production_final_resolved_identity_count_including_automated_entities": manifest["final_resolved_identity_count"],
            "hidden_distinct_entities_including_automated_entities": len(total_person_counts),
            "hidden_distinct_humans": sum(1 for person_id in total_person_counts if person_types[person_id] == "human"),
            "automated_entities_not_removed_by_production_clustering": True,
        },
        "inputs": {
            "assignment_sha256": _sha256(assignments_path),
            "production_assignment_sha256_matches": _sha256(assignments_path) == manifest["assignment_output"]["sha256"],
        },
        "isolation": {
            "labels_used_after_clustering_only": True,
            "labels_used_to_form_or_reject_components": False,
            "overall_accuracy_reported": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cluster_evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output_dir / "cluster_evaluation.md").write_text(_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assignments", type=Path, default=Path("outputs/clustering/cluster_assignments.csv.gz"))
    parser.add_argument("--clustering-manifest", type=Path, default=Path("outputs/clustering/clustering_manifest.json"))
    parser.add_argument("--truth-map", type=Path, default=Path("data/generated/person_map.csv"))
    parser.add_argument("--canonical-links", type=Path, default=Path("data/generated/hidden/canonical_duplicate_links.jsonl"))
    parser.add_argument("--hard-negatives", type=Path, default=Path("data/generated/hard_negatives.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/clustering"))
    args = parser.parse_args()
    try:
        result = evaluate_clusters(
            args.assignments,
            args.clustering_manifest,
            args.truth_map,
            args.canonical_links,
            args.hard_negatives,
            args.output_dir,
        )
    except ClusterEvaluationError as exc:
        print(f"[cluster-evaluation] ERROR: {exc}")
        return 1
    metrics = result["pairwise_cluster_metrics"]
    print(
        f"[cluster-evaluation] Precision {_percentage(metrics['precision'])}; "
        f"false merged pairs {metrics['false_positive_merged_pairs']:,}; "
        f"quarantined components {result['quarantine_evaluation']['component_count']:,}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
