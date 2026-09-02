"""Compare preserved heuristic clusters with selected-logistic challenger clusters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


class ClusterComparisonError(ValueError):
    """Raised when cluster artifacts are incomplete or fail promotion checks."""


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClusterComparisonError(f"Unable to load {path}: {exc}") from exc


def promotion_checks(
    baseline_manifest: Mapping[str, Any],
    baseline_evaluation: Mapping[str, Any],
    challenger_manifest: Mapping[str, Any],
    challenger_evaluation: Mapping[str, Any],
) -> dict[str, bool]:
    baseline_pairs = baseline_evaluation["pairwise_cluster_metrics"]
    challenger_pairs = challenger_evaluation["pairwise_cluster_metrics"]
    challenger_purity = challenger_evaluation["accepted_cluster_purity"]
    challenger_hard = challenger_evaluation["hard_negative_metrics"]
    maximum = int(challenger_manifest["rule1_maximum_source_records"])
    return {
        "same_physical_record_population": challenger_manifest["total_source_records"]
        == baseline_manifest["total_source_records"],
        "cluster_precision_not_lower": challenger_pairs["precision"] is not None
        and baseline_pairs["precision"] is not None
        and challenger_pairs["precision"] >= baseline_pairs["precision"],
        "zero_false_merged_pairs": challenger_pairs["false_positive_merged_pairs"] == 0,
        "zero_mixed_person_components": challenger_purity["mixed_person_components"] == 0,
        "zero_hard_negatives_co_clustered": challenger_hard["co_clustered_after_transitivity"] == 0,
        "rule1_applied_without_partial_merges": challenger_manifest["partial_merges_from_quarantined_components"] == 0,
        "accepted_components_respect_size_cap": challenger_manifest["largest_accepted_component_size"] <= maximum,
        "human_pairwise_recall_not_lower": challenger_pairs["recall_humans"]
        >= baseline_pairs["recall_humans"],
    }


def _summary(manifest: Mapping[str, Any], evaluation: Mapping[str, Any]) -> dict[str, Any]:
    pairs = evaluation["pairwise_cluster_metrics"]
    purity = evaluation["accepted_cluster_purity"]
    hard = evaluation["hard_negative_metrics"]
    canonical = evaluation["canonical_link_metrics"]
    return {
        "auto_merge_edges": manifest["auto_merge_edges"],
        "final_resolved_identity_count": manifest["final_resolved_identity_count"],
        "accepted_merged_component_count": manifest["accepted_merged_component_count"],
        "accepted_singleton_count": manifest["accepted_singleton_count"],
        "quarantined_component_count": manifest["quarantined_component_count"],
        "quarantined_record_count": manifest["quarantined_record_count"],
        "largest_accepted_component_size": manifest["largest_accepted_component_size"],
        "predicted_merged_pairs": pairs["predicted_merged_pairs"],
        "false_positive_merged_pairs": pairs["false_positive_merged_pairs"],
        "cluster_precision": pairs["precision"],
        "human_pairwise_recall": pairs["recall_humans"],
        "mixed_person_components": purity["mixed_person_components"],
        "hard_negatives_co_clustered": hard["co_clustered_after_transitivity"],
        "recoverable_canonical_links_accepted": canonical["recoverable_accepted_cluster_links"],
    }


def _report(result: Mapping[str, Any]) -> str:
    baseline = result["heuristic_baseline"]
    challenger = result["logistic_challenger"]
    lines = [
        "# Heuristic versus logistic clustering comparison",
        "",
        f"**Promotion decision:** {result['promotion_decision']}",
        "",
        "| Metric | Heuristic baseline | Logistic challenger | Change |",
        "|---|---:|---:|---:|",
        f"| Auto-merge edges | {baseline['auto_merge_edges']:,} | {challenger['auto_merge_edges']:,} | {challenger['auto_merge_edges'] - baseline['auto_merge_edges']:+,} |",
        f"| Final resolved identities | {baseline['final_resolved_identity_count']:,} | {challenger['final_resolved_identity_count']:,} | {challenger['final_resolved_identity_count'] - baseline['final_resolved_identity_count']:+,} |",
        f"| Accepted merged components | {baseline['accepted_merged_component_count']:,} | {challenger['accepted_merged_component_count']:,} | {challenger['accepted_merged_component_count'] - baseline['accepted_merged_component_count']:+,} |",
        f"| Accepted singleton components | {baseline['accepted_singleton_count']:,} | {challenger['accepted_singleton_count']:,} | {challenger['accepted_singleton_count'] - baseline['accepted_singleton_count']:+,} |",
        f"| Implied merged record pairs | {baseline['predicted_merged_pairs']:,} | {challenger['predicted_merged_pairs']:,} | {challenger['predicted_merged_pairs'] - baseline['predicted_merged_pairs']:+,} |",
        f"| False merged record pairs | {baseline['false_positive_merged_pairs']:,} | {challenger['false_positive_merged_pairs']:,} | {challenger['false_positive_merged_pairs'] - baseline['false_positive_merged_pairs']:+,} |",
        f"| Cluster precision | {baseline['cluster_precision']:.4%} | {challenger['cluster_precision']:.4%} | {(challenger['cluster_precision'] - baseline['cluster_precision']) * 100:+.4f} pp |",
        f"| Human pairwise recall | {baseline['human_pairwise_recall']:.4%} | {challenger['human_pairwise_recall']:.4%} | {(challenger['human_pairwise_recall'] - baseline['human_pairwise_recall']) * 100:+.4f} pp |",
        f"| Mixed-person components | {baseline['mixed_person_components']:,} | {challenger['mixed_person_components']:,} | {challenger['mixed_person_components'] - baseline['mixed_person_components']:+,} |",
        f"| Hard negatives co-clustered | {baseline['hard_negatives_co_clustered']:,} | {challenger['hard_negatives_co_clustered']:,} | {challenger['hard_negatives_co_clustered'] - baseline['hard_negatives_co_clustered']:+,} |",
        f"| Rule 1 quarantined components | {baseline['quarantined_component_count']:,} | {challenger['quarantined_component_count']:,} | {challenger['quarantined_component_count'] - baseline['quarantined_component_count']:+,} |",
        f"| Largest accepted component | {baseline['largest_accepted_component_size']:,} | {challenger['largest_accepted_component_size']:,} | {challenger['largest_accepted_component_size'] - baseline['largest_accepted_component_size']:+,} |",
        "",
        "## Promotion gates",
        "",
    ]
    lines.extend(
        f"- {'PASS' if passed else 'FAIL'}: `{name}`"
        for name, passed in result["promotion_checks"].items()
    )
    lines.extend(
        [
            "",
            "The operational identity count includes automated traffic. It is not presented as the final number of human customers; bot/test handling and review-queue uncertainty remain separate business-analysis steps.",
            "",
        ]
    )
    return "\n".join(lines)


def compare_clusters(
    baseline_dir: Path,
    challenger_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    baseline_manifest = _load(Path(baseline_dir) / "clustering_manifest.json")
    baseline_evaluation = _load(Path(baseline_dir) / "cluster_evaluation.json")
    challenger_manifest = _load(Path(challenger_dir) / "clustering_manifest.json")
    challenger_evaluation = _load(Path(challenger_dir) / "cluster_evaluation.json")
    checks = promotion_checks(
        baseline_manifest,
        baseline_evaluation,
        challenger_manifest,
        challenger_evaluation,
    )
    passed = all(checks.values())
    result: dict[str, Any] = {
        "phase": "selected_mct_cluster_comparison",
        "baseline_model": "heuristic_mct",
        "challenger_model": "logistic_regression_mct",
        "promotion_decision": "promote_logistic_clusters" if passed else "retain_heuristic_clusters",
        "promotion_checks": checks,
        "all_promotion_checks_passed": passed,
        "heuristic_baseline": _summary(baseline_manifest, baseline_evaluation),
        "logistic_challenger": _summary(challenger_manifest, challenger_evaluation),
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "cluster_comparison.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "cluster_comparison.md").write_text(_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=Path("outputs/clustering"))
    parser.add_argument("--challenger-dir", type=Path, default=Path("outputs/logistic-clustering"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/logistic-clustering"))
    args = parser.parse_args()
    try:
        result = compare_clusters(args.baseline_dir, args.challenger_dir, args.output_dir)
    except ClusterComparisonError as exc:
        print(f"[cluster-comparison] ERROR: {exc}")
        return 1
    print(
        f"[cluster-comparison] {result['promotion_decision']}; "
        f"checks_passed={sum(result['promotion_checks'].values())}/{len(result['promotion_checks'])}"
    )
    return 0 if result["all_promotion_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
