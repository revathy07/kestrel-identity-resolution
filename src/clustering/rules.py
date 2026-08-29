"""Pure helpers for deterministic connected components and Rule 1."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


DEFAULT_RULES = Path(__file__).resolve().parents[2] / "config" / "clustering_rules.yaml"


class ClusteringError(ValueError):
    """Raised when clustering inputs or configuration violate the contract."""


class UnionFind:
    """Deterministic disjoint-set structure with union by size."""

    def __init__(self, count: int) -> None:
        self.parent = list(range(count))
        self.size = [1] * count

    def find(self, node: int) -> int:
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def union(self, left: int, right: int) -> int:
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


def load_clustering_rules(path: Path = DEFAULT_RULES) -> dict[str, Any]:
    try:
        rules = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClusteringError(f"Unable to load clustering rules from {path}: {exc}") from exc
    required = {
        "version",
        "auto_merge_minimum",
        "accepted_edge_decision",
        "maximum_accepted_source_records",
        "oversized_component_action",
    }
    missing = required - set(rules) if isinstance(rules, dict) else required
    if missing:
        raise ClusteringError(f"Clustering configuration is missing: {sorted(missing)}")
    if not math.isclose(float(rules["auto_merge_minimum"]), 0.88):
        raise ClusteringError("The assessment's auto-merge threshold must remain exactly 0.88")
    if int(rules["maximum_accepted_source_records"]) != 12:
        raise ClusteringError("Rule 1 requires a maximum accepted component size of exactly 12")
    if rules["accepted_edge_decision"] != "auto_merge":
        raise ClusteringError("Only auto-merge decisions may form cluster edges")
    if rules["oversized_component_action"] != "reject_in_full_and_quarantine":
        raise ClusteringError("Oversized components must be rejected in full and quarantined")
    return rules


def stable_component_id(
    records: Iterable[tuple[str, int, str]], *, prefix: str = "KIR"
) -> str:
    digest = hashlib.sha256()
    for source, ordinal, record_id in sorted(records):
        for part in (source, str(ordinal), record_id):
            encoded = part.encode("utf-8")
            digest.update(len(encoded).to_bytes(4, "big"))
            digest.update(encoded)
    return f"{prefix}-{digest.hexdigest()[:20]}"


def component_status(size: int, maximum: int = 12) -> str:
    if size < 1:
        raise ClusteringError("A connected component cannot be empty")
    if size > maximum:
        return "quarantined_oversized"
    return "accepted_singleton" if size == 1 else "accepted_merged"
