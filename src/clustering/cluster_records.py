"""Form transitive components from MCT auto-merge edges and enforce Rule 1.

Every component with more than 12 physical source records is rejected in full and
quarantined. This production command reads no evaluation labels.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.clustering.rules import (
    DEFAULT_RULES,
    ClusteringError,
    UnionFind,
    component_status,
    load_clustering_rules,
    stable_component_id,
)


CLUSTERER_VERSION = 1
ASSIGNMENT_COLUMNS = [
    "source",
    "record_ordinal",
    "source_record_id",
    "proposed_component_id",
    "proposed_component_size",
    "final_cluster_id",
    "cluster_status",
]


@dataclass(frozen=True)
class SourceRecord:
    source: str
    ordinal: int
    source_record_id: str


@dataclass(frozen=True)
class AutoEdge:
    left: int
    right: int
    score: float
    evidence: tuple[str, ...]
    conflicts: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _load_source_records(path: Path) -> tuple[list[SourceRecord], dict[tuple[str, int], int]]:
    required = {"source", "record_ordinal", "source_record_id"}
    records: list[SourceRecord] = []
    index: dict[tuple[str, int], int] = {}
    previous: tuple[str, int] | None = None
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ClusteringError(
                    f"Normalized input is missing columns: {sorted(required - set(reader.fieldnames or []))}"
                )
            for row in reader:
                try:
                    key = (row["source"], int(row["record_ordinal"]))
                except (TypeError, ValueError) as exc:
                    raise ClusteringError(f"Invalid normalized record identity: {row}") from exc
                if key == previous:
                    if records[-1].source_record_id != row["source_record_id"]:
                        raise ClusteringError(f"Conflicting source record IDs for {key}")
                    continue
                if key in index:
                    raise ClusteringError(f"Normalized observations for record {key} are not contiguous")
                index[key] = len(records)
                records.append(SourceRecord(key[0], key[1], row["source_record_id"]))
                previous = key
    except OSError as exc:
        raise ClusteringError(f"Unable to read normalized records {path}: {exc}") from exc
    return records, index


def _read_edges(
    path: Path,
    records: list[SourceRecord],
    record_index: Mapping[tuple[str, int], int],
    union_find: UnionFind,
    rules: Mapping[str, Any],
) -> tuple[list[AutoEdge], Counter[str]]:
    required = {
        "left_source",
        "left_record_ordinal",
        "left_source_record_id",
        "right_source",
        "right_record_ordinal",
        "right_source_record_id",
        "positive_evidence",
        "conflicts",
        "mct_score",
        "decision",
    }
    decisions: Counter[str] = Counter()
    edges: list[AutoEdge] = []
    auto_minimum = float(rules["auto_merge_minimum"])
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ClusteringError(
                    f"Scored input is missing columns: {sorted(required - set(reader.fieldnames or []))}"
                )
            for row_number, row in enumerate(reader, start=1):
                try:
                    left_key = (row["left_source"], int(row["left_record_ordinal"]))
                    right_key = (row["right_source"], int(row["right_record_ordinal"]))
                    left_index, right_index = record_index[left_key], record_index[right_key]
                    score = float(row["mct_score"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ClusteringError(f"Invalid scored pair at row {row_number}: {exc}") from exc
                if records[left_index].source_record_id != row["left_source_record_id"] or records[right_index].source_record_id != row["right_source_record_id"]:
                    raise ClusteringError(f"Scored-to-normalized record ID mismatch at row {row_number}")
                decision = row["decision"]
                decisions[decision] += 1
                if decision == "auto_merge":
                    if score < auto_minimum:
                        raise ClusteringError(f"Auto-merge row {row_number} has MCT {score} below {auto_minimum}")
                    union_find.union(left_index, right_index)
                    edges.append(
                        AutoEdge(
                            left_index,
                            right_index,
                            score,
                            tuple(filter(None, row["positive_evidence"].split(";"))),
                            tuple(filter(None, row["conflicts"].split(";"))),
                        )
                    )
                elif decision == "human_review":
                    if not 0.62 <= score < auto_minimum:
                        raise ClusteringError(f"Review row {row_number} has inconsistent MCT {score}")
                elif decision == "leave_separate":
                    if not score < 0.62:
                        raise ClusteringError(f"Separate row {row_number} has inconsistent MCT {score}")
                else:
                    raise ClusteringError(f"Unknown decision {decision!r} at scored row {row_number}")
    except OSError as exc:
        raise ClusteringError(f"Unable to read scored pairs {path}: {exc}") from exc
    return edges, decisions


def _open_assignments(path: Path) -> tuple[Any, Any, csv.DictWriter]:
    binary = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=ASSIGNMENT_COLUMNS)
    writer.writeheader()
    return binary, text, writer


def _write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _report(manifest: Mapping[str, Any], distribution: list[dict[str, Any]], quarantine: list[dict[str, Any]]) -> str:
    largest = manifest["largest_proposed_component"]
    return "\n".join(
        [
            "# Phase 7 capped-clustering report",
            "",
            "## Outcome",
            "",
            f"- Physical source records: **{manifest['total_source_records']:,}**",
            f"- MCT auto-merge edges consumed: **{manifest['auto_merge_edges']:,}**",
            f"- Proposed connected components: **{manifest['proposed_component_count']:,}**",
            f"- Accepted merged components: **{manifest['accepted_merged_component_count']:,}**",
            f"- Accepted singleton components: **{manifest['accepted_singleton_count']:,}**",
            f"- Components rejected by Rule 1: **{manifest['quarantined_component_count']:,}**",
            f"- Records quarantined: **{manifest['quarantined_record_count']:,}**",
            f"- Final resolved identity records: **{manifest['final_resolved_identity_count']:,}**",
            "",
            "## Rule 1",
            "",
            "Components containing up to and including 12 physical source records are accepted. Any component containing 13 or more is rejected in full and quarantined. Its members receive no final cluster ID, none of its edges are partially retained, and the MCT threshold is not changed.",
            "",
            "## Component-size distribution",
            "",
            _table(
                ["Size", "Status", "Components", "Records"],
                [[row["component_size"], row["cluster_status"], f"{row['component_count']:,}", f"{row['record_count']:,}"] for row in distribution],
            ),
            "",
            "## Largest proposed component",
            "",
            f"The largest proposed component contains **{largest['source_record_count']:,}** source records and **{largest['auto_merge_edge_count']:,}** auto-merge edges. Its source composition is `{json.dumps(largest['source_counts'], sort_keys=True)}` and its status is `{largest['cluster_status']}`.",
            "",
            "## Quarantine",
            "",
            (
                f"The quarantine summary contains {len(quarantine):,} oversized components. Evaluation-only truth content is reported separately."
                if quarantine
                else "No component exceeded the 12-record cap; the quarantine is empty."
            ),
            "",
            "## Isolation and handoff",
            "",
            "Production clustering reads only normalized record identity, Phase 6 scores and configuration. Hidden labels are opened later by the separate cluster evaluator. Human-review edges are not merged. Final business counts still need interpretation of the review queue and automated traffic.",
            "",
        ]
    )


def cluster_records(
    normalized_path: Path,
    scored_path: Path,
    output_dir: Path,
    *,
    rules_path: Path = DEFAULT_RULES,
    show_progress: bool = True,
) -> dict[str, Any]:
    normalized_path = Path(normalized_path)
    scored_path = Path(scored_path)
    output_dir = Path(output_dir)
    rules_path = Path(rules_path)
    for path in (normalized_path, scored_path, rules_path):
        if not path.exists():
            raise ClusteringError(f"Required clustering input not found: {path}")
    rules = load_clustering_rules(rules_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    if show_progress:
        print("[clustering] Registering all normalized physical records...")
    records, record_index = _load_source_records(normalized_path)
    union_find = UnionFind(len(records))
    if show_progress:
        print("[clustering] Forming components from MCT auto-merge edges...")
    edges, decision_counts = _read_edges(scored_path, records, record_index, union_find, rules)
    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        components[union_find.find(index)].append(index)

    edges_by_root: dict[int, list[AutoEdge]] = defaultdict(list)
    for edge in edges:
        root = union_find.find(edge.left)
        if root != union_find.find(edge.right):
            raise ClusteringError("An auto-merge edge crosses final connected components")
        edges_by_root[root].append(edge)

    maximum = int(rules["maximum_accepted_source_records"])
    component_metadata: dict[int, dict[str, Any]] = {}
    distribution_counts: Counter[tuple[int, str]] = Counter()
    quarantine_rows: list[dict[str, Any]] = []
    accepted_singletons = accepted_merged = quarantined_components = quarantined_records = 0
    accepted_edges = rejected_edges = records_collapsed = 0
    largest_root = max(components, key=lambda root: (len(components[root]), -root)) if components else None
    for root, members in components.items():
        source_records = [records[index] for index in members]
        identities = [(item.source, item.ordinal, item.source_record_id) for item in source_records]
        size = len(members)
        status = component_status(size, maximum)
        proposed_id = stable_component_id(identities, prefix="CMP")
        final_id = stable_component_id(identities, prefix="KIR") if status != "quarantined_oversized" else ""
        component_edges = edges_by_root[root]
        component_metadata[root] = {
            "status": status,
            "size": size,
            "proposed_id": proposed_id,
            "final_id": final_id,
        }
        distribution_counts[(size, status)] += 1
        if status == "accepted_singleton":
            accepted_singletons += 1
        elif status == "accepted_merged":
            accepted_merged += 1
            accepted_edges += len(component_edges)
            records_collapsed += size - 1
        else:
            quarantined_components += 1
            quarantined_records += size
            rejected_edges += len(component_edges)
            evidence = Counter(feature for edge in component_edges for feature in edge.evidence)
            conflicts = Counter(conflict for edge in component_edges for conflict in edge.conflicts)
            scores = [edge.score for edge in component_edges]
            quarantine_rows.append(
                {
                    "proposed_component_id": proposed_id,
                    "source_record_count": size,
                    "auto_merge_edge_count": len(component_edges),
                    "source_counts": json.dumps(dict(sorted(Counter(item.source for item in source_records).items())), sort_keys=True),
                    "minimum_mct": f"{min(scores):.6f}" if scores else "",
                    "maximum_mct": f"{max(scores):.6f}" if scores else "",
                    "mean_mct": f"{sum(scores) / len(scores):.6f}" if scores else "",
                    "evidence_features": json.dumps(dict(sorted(evidence.items())), sort_keys=True),
                    "conflicts": json.dumps(dict(sorted(conflicts.items())), sort_keys=True),
                    "rule1_action": "rejected_in_full_and_quarantined",
                    "partial_merge_performed": "false",
                }
            )

    assignment_path = output_dir / "cluster_assignments.csv.gz"
    binary, text_handle, writer = _open_assignments(assignment_path)
    try:
        for index, record in enumerate(records):
            metadata = component_metadata[union_find.find(index)]
            writer.writerow(
                {
                    "source": record.source,
                    "record_ordinal": record.ordinal,
                    "source_record_id": record.source_record_id,
                    "proposed_component_id": metadata["proposed_id"],
                    "proposed_component_size": metadata["size"],
                    "final_cluster_id": metadata["final_id"],
                    "cluster_status": metadata["status"],
                }
            )
    finally:
        text_handle.close()
        binary.close()

    distribution_rows = [
        {
            "component_size": size,
            "cluster_status": status,
            "component_count": count,
            "record_count": size * count,
        }
        for (size, status), count in sorted(distribution_counts.items())
    ]
    _write_csv(
        output_dir / "cluster_size_distribution.csv",
        distribution_rows,
        ["component_size", "cluster_status", "component_count", "record_count"],
    )
    quarantine_rows.sort(key=lambda row: (-int(row["source_record_count"]), row["proposed_component_id"]))
    _write_csv(
        output_dir / "quarantined_components.csv",
        quarantine_rows,
        [
            "proposed_component_id",
            "source_record_count",
            "auto_merge_edge_count",
            "source_counts",
            "minimum_mct",
            "maximum_mct",
            "mean_mct",
            "evidence_features",
            "conflicts",
            "rule1_action",
            "partial_merge_performed",
        ],
    )
    largest_members = components[largest_root] if largest_root is not None else []
    largest_records = [records[index] for index in largest_members]
    largest_edges = edges_by_root[largest_root] if largest_root is not None else []
    largest_status = component_status(len(largest_members), maximum) if largest_members else None
    final_identity_count = len(components) - quarantined_components + quarantined_records
    manifest: dict[str, Any] = {
        "phase": "capped_transitive_clustering",
        "clusterer_version": CLUSTERER_VERSION,
        "rule1_maximum_source_records": maximum,
        "total_source_records": len(records),
        "scored_pair_decision_counts": dict(decision_counts),
        "auto_merge_edges": len(edges),
        "proposed_component_count": len(components),
        "accepted_component_count": accepted_singletons + accepted_merged,
        "accepted_singleton_count": accepted_singletons,
        "accepted_merged_component_count": accepted_merged,
        "accepted_auto_merge_edges": accepted_edges,
        "records_collapsed_by_accepted_merges": records_collapsed,
        "quarantined_component_count": quarantined_components,
        "quarantined_record_count": quarantined_records,
        "rejected_auto_merge_edges": rejected_edges,
        "partial_merges_from_quarantined_components": 0,
        "threshold_adjustments_for_rule1": 0,
        "final_resolved_identity_count": final_identity_count,
        "largest_accepted_component_size": max(
            (metadata["size"] for metadata in component_metadata.values() if metadata["status"] != "quarantined_oversized"),
            default=0,
        ),
        "largest_proposed_component": {
            "proposed_component_id": component_metadata[largest_root]["proposed_id"] if largest_root is not None else None,
            "source_record_count": len(largest_members),
            "auto_merge_edge_count": len(largest_edges),
            "source_counts": dict(sorted(Counter(item.source for item in largest_records).items())),
            "cluster_status": largest_status,
            "evidence_features": dict(sorted(Counter(feature for edge in largest_edges for feature in edge.evidence).items())),
        },
        "inputs": {
            "normalized": {"path": _portable_path(normalized_path), "sha256": _sha256(normalized_path)},
            "scored_pairs": {"path": _portable_path(scored_path), "sha256": _sha256(scored_path)},
            "configuration": {"path": _portable_path(rules_path), "sha256": _sha256(rules_path)},
        },
        "assignment_output": {
            "path": assignment_path.name,
            "compression": "gzip",
            "rows": len(records),
            "size_bytes": assignment_path.stat().st_size,
            "sha256": _sha256(assignment_path),
        },
        "phase_boundaries": {
            "transitive_merging_performed": True,
            "rule1_cluster_size_cap_applied": True,
            "oversized_components_partially_merged": False,
            "evaluation_labels_read": False,
            "human_review_pairs_merged": False,
        },
    }
    (output_dir / "clustering_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output_dir / "clustering_report.md").write_text(_report(manifest, distribution_rows, quarantine_rows), encoding="utf-8")
    if show_progress:
        print(
            f"[clustering] Complete: {len(components):,} proposed components; "
            f"{quarantined_components:,} quarantined; {final_identity_count:,} final identities"
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized-path", type=Path, default=Path("outputs/normalization/normalized_identifiers.csv.gz"))
    parser.add_argument("--scored-path", type=Path, default=Path("outputs/scoring/scored_candidate_pairs.csv.gz"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/clustering"))
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()
    try:
        cluster_records(args.normalized_path, args.scored_path, args.output_dir, rules_path=args.rules)
    except ClusteringError as exc:
        print(f"[clustering] ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
