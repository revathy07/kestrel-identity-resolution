"""Evaluate a frozen business estimate against hidden synthetic truth.

This module is deliberately separate from ``src.business.estimate_customers``.  The
production estimator never imports it and never reads ``person_map.csv``.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


class BusinessEstimateEvaluationError(ValueError):
    """Raised when frozen-estimate evaluation inputs do not reconcile."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def load_truth(path: Path) -> tuple[dict[tuple[str, str], tuple[str, str]], dict[str, set[str]]]:
    """Load hidden truth without returning physical-row identifiers in any output."""

    by_record: dict[tuple[str, str], tuple[str, str]] = {}
    people: dict[str, set[str]] = defaultdict(set)
    try:
        with Path(path).open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"system", "record_id", "person_id", "entity_type"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise BusinessEstimateEvaluationError(f"Truth map missing: {sorted(missing)}")
            for row in reader:
                key = (row["system"], row["record_id"])
                value = (row["person_id"], row["entity_type"])
                previous = by_record.get(key)
                if previous is not None and previous != value:
                    raise BusinessEstimateEvaluationError(
                        f"One source record maps to conflicting hidden entities: {key}"
                    )
                by_record[key] = value
                people[row["entity_type"]].add(row["person_id"])
    except OSError as exc:
        raise BusinessEstimateEvaluationError(f"Unable to read truth map: {exc}") from exc
    return by_record, dict(people)


def evaluate_classifications(
    truth_by_record: Mapping[tuple[str, str], tuple[str, str]],
    rows: Iterable[Mapping[str, str]],
) -> dict[str, Any]:
    """Compare observable record/cluster policies with hidden entity types."""

    row_counts: Counter[str] = Counter()
    cluster_policies: dict[str, Counter[str]] = defaultdict(Counter)
    cluster_types: dict[str, Counter[str]] = defaultdict(Counter)
    cluster_people: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    seen_rows = 0
    for row in rows:
        key = (row["source"], row["source_record_id"])
        truth = truth_by_record.get(key)
        if truth is None:
            raise BusinessEstimateEvaluationError(f"Classification row missing from truth: {key}")
        person_id, entity_type = truth
        if entity_type not in {"human", "bot"}:
            raise BusinessEstimateEvaluationError(f"Unsupported hidden entity type: {entity_type}")
        policy = row["observable_policy"]
        if policy not in {"none", "automation", "internal_qa"}:
            raise BusinessEstimateEvaluationError(f"Unsupported observable policy: {policy}")
        cluster = row["final_cluster_id"]
        row_counts[f"truth_{entity_type}"] += 1
        row_counts[f"policy_{policy}"] += 1
        if policy == "automation" and entity_type == "bot":
            row_counts["automation_true_positive"] += 1
        elif policy == "automation":
            row_counts["automation_false_positive"] += 1
        elif entity_type == "bot":
            row_counts["automation_false_negative"] += 1
        cluster_policies[cluster][policy] += 1
        cluster_types[cluster][entity_type] += 1
        cluster_people[cluster][entity_type].add(person_id)
        seen_rows += 1

    excluded_automation: set[str] = set()
    excluded_qa: set[str] = set()
    mixed_policy: set[str] = set()
    for cluster, policies in cluster_policies.items():
        size = sum(policies.values())
        if policies["automation"] == size:
            excluded_automation.add(cluster)
        elif policies["internal_qa"] == size:
            excluded_qa.add(cluster)
        elif policies["automation"] or policies["internal_qa"]:
            mixed_policy.add(cluster)

    excluded_auto_people: dict[str, set[str]] = defaultdict(set)
    auto_cluster_truth: Counter[str] = Counter()
    for cluster in excluded_automation:
        types = cluster_types[cluster]
        if types["bot"] and not types["human"]:
            auto_cluster_truth["pure_bot"] += 1
        elif types["human"] and not types["bot"]:
            auto_cluster_truth["pure_human"] += 1
        else:
            auto_cluster_truth["mixed"] += 1
        for entity_type, identifiers in cluster_people[cluster].items():
            excluded_auto_people[entity_type].update(identifiers)

    excluded_qa_people: dict[str, set[str]] = defaultdict(set)
    qa_cluster_truth: Counter[str] = Counter()
    for cluster in excluded_qa:
        types = cluster_types[cluster]
        if types["human"] and not types["bot"]:
            qa_cluster_truth["pure_human"] += 1
        elif types["bot"] and not types["human"]:
            qa_cluster_truth["pure_bot"] += 1
        else:
            qa_cluster_truth["mixed"] += 1
        for entity_type, identifiers in cluster_people[cluster].items():
            excluded_qa_people[entity_type].update(identifiers)

    tp = row_counts["automation_true_positive"]
    fp = row_counts["automation_false_positive"]
    fn = row_counts["automation_false_negative"]
    return {
        "classified_records": seen_rows,
        "truth_record_counts": {
            "human": row_counts["truth_human"],
            "bot": row_counts["truth_bot"],
        },
        "automation_record_metrics": {
            "true_positive_bot_records": tp,
            "false_positive_human_records": fp,
            "false_negative_bot_records": fn,
            "precision": _rate(tp, tp + fp),
            "recall": _rate(tp, tp + fn),
        },
        "automation_cluster_metrics": {
            "excluded_clusters": len(excluded_automation),
            "pure_bot_clusters": auto_cluster_truth["pure_bot"],
            "pure_human_clusters": auto_cluster_truth["pure_human"],
            "mixed_truth_clusters": auto_cluster_truth["mixed"],
            "distinct_bot_entities_excluded": len(excluded_auto_people["bot"]),
            "distinct_human_entities_excluded": len(excluded_auto_people["human"]),
        },
        "internal_qa_policy_audit": {
            "excluded_clusters": len(excluded_qa),
            "pure_human_clusters": qa_cluster_truth["pure_human"],
            "pure_bot_clusters": qa_cluster_truth["pure_bot"],
            "mixed_truth_clusters": qa_cluster_truth["mixed"],
            "distinct_human_entities_excluded": len(excluded_qa_people["human"]),
            "distinct_bot_entities_excluded": len(excluded_qa_people["bot"]),
            "note": "QA is an observable business policy; the supplied truth has no independent QA label.",
        },
        "mixed_policy_clusters_retained": len(mixed_policy),
    }


def _percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4%}"


def _report(result: Mapping[str, Any]) -> str:
    count = result["count_coverage"]
    auto = result["automation_detection"]["automation_record_metrics"]
    clusters = result["automation_detection"]["automation_cluster_metrics"]
    qa = result["automation_detection"]["internal_qa_policy_audit"]
    status = "PASS" if count["defensible_range_contains_true_human_count"] else "REVISE"
    return "\n".join(
        [
            "# Phase 13 hidden-truth evaluation",
            "",
            f"**Count-range result: {status}.** The frozen defensible range "
            f"{count['defensible_range_lower']:,}–{count['defensible_range_upper']:,} "
            f"{'contains' if status == 'PASS' else 'does not contain'} the synthetic truth of "
            f"{count['true_human_entities']:,} human entities.",
            "",
            "## Estimate accuracy",
            "",
            f"The recommended estimate is **{count['recommended_estimate']:,}**, an absolute "
            f"error of **{count['absolute_error']:,}** ({_percentage(count['absolute_percentage_error'])}).",
            "This diagnostic is opened after freezing; it is not an input to production scoring, "
            "traffic classification or Monte Carlo calibration.",
            "",
            "## Observable automation detector",
            "",
            f"Record precision is **{_percentage(auto['precision'])}** and recall is "
            f"**{_percentage(auto['recall'])}**. The all-members rule excludes "
            f"**{clusters['excluded_clusters']:,}** clusters: "
            f"{clusters['pure_bot_clusters']:,} pure-bot, "
            f"{clusters['pure_human_clusters']:,} pure-human and "
            f"{clusters['mixed_truth_clusters']:,} mixed-truth clusters.",
            "",
            "## Internal QA policy audit",
            "",
            f"The observable QA policy excludes **{qa['excluded_clusters']:,}** clusters "
            f"representing **{qa['distinct_human_entities_excluded']:,}** hidden human entities. "
            "The truth map has no independent QA label, so this is a policy audit, not claimed "
            "QA-classifier precision.",
            "",
            "## Isolation conclusion",
            "",
            "The estimator manifest states that it did not read hidden person IDs or entity types. "
            "This evaluator is the only Phase 13 component that opens `person_map.csv`.",
            "",
        ]
    )


def evaluate_business_estimate(
    estimate_path: Path,
    classification_path: Path,
    truth_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    estimate = json.loads(Path(estimate_path).read_text(encoding="utf-8"))
    expected_hash = estimate["classification_output"]["sha256"]
    actual_hash = _sha256(classification_path)
    if actual_hash != expected_hash:
        raise BusinessEstimateEvaluationError(
            "Classification hash differs from the frozen estimate manifest"
        )
    if not estimate.get("isolation", {}).get("person_map_read") is False:
        raise BusinessEstimateEvaluationError("Estimate does not assert person-map isolation")

    truth_by_record, people = load_truth(truth_path)
    try:
        with gzip.open(classification_path, "rt", encoding="utf-8", newline="") as handle:
            detection = evaluate_classifications(truth_by_record, csv.DictReader(handle))
    except OSError as exc:
        raise BusinessEstimateEvaluationError(f"Unable to read classifications: {exc}") from exc

    if detection["classified_records"] != estimate["classification_output"]["rows"]:
        raise BusinessEstimateEvaluationError("Classification row count differs from manifest")
    exclusions = estimate["observable_traffic_exclusions"]
    if detection["automation_cluster_metrics"]["excluded_clusters"] != exclusions["automation_clusters"]:
        raise BusinessEstimateEvaluationError("Automation cluster count does not reconcile")
    if detection["internal_qa_policy_audit"]["excluded_clusters"] != exclusions["internal_qa_clusters"]:
        raise BusinessEstimateEvaluationError("QA cluster count does not reconcile")

    true_humans = len(people.get("human", set()))
    true_bots = len(people.get("bot", set()))
    auto_clusters = detection["automation_cluster_metrics"]
    auto_clusters["entity_recall"] = _rate(auto_clusters["distinct_bot_entities_excluded"], true_bots)
    count = estimate["customer_count_estimate"]
    recommended = int(count["recommended_candidate_resolvable_count"])
    lower = int(count["defensible_range_lower"])
    upper = int(count["defensible_range_upper"])
    result = {
        "phase": "business_customer_count_hidden_truth_evaluation",
        "evaluation_opened_after_estimate_freeze": True,
        "count_coverage": {
            "true_human_entities": true_humans,
            "true_automated_entities": true_bots,
            "recommended_estimate": recommended,
            "signed_error": recommended - true_humans,
            "absolute_error": abs(recommended - true_humans),
            "absolute_percentage_error": _rate(abs(recommended - true_humans), true_humans),
            "defensible_range_lower": lower,
            "defensible_range_upper": upper,
            "defensible_range_contains_true_human_count": lower <= true_humans <= upper,
        },
        "automation_detection": detection,
        "inputs": {
            "estimate": {"path": Path(estimate_path).as_posix(), "sha256": _sha256(estimate_path)},
            "classification": {"path": Path(classification_path).as_posix(), "sha256": actual_hash},
            "hidden_truth": {"path": Path(truth_path).as_posix(), "sha256": _sha256(truth_path)},
        },
        "hidden_identifiers_emitted": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "business_estimate_evaluation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "business_estimate_evaluation.md").write_text(
        _report(result), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--estimate", type=Path, default=Path("outputs/business/business_estimate.json"))
    parser.add_argument(
        "--classifications",
        type=Path,
        default=Path("outputs/business/observable_traffic_records.csv.gz"),
    )
    parser.add_argument("--truth-map", type=Path, default=Path("data/generated/person_map.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/business"))
    args = parser.parse_args()
    try:
        result = evaluate_business_estimate(
            args.estimate, args.classifications, args.truth_map, args.output_dir
        )
    except (BusinessEstimateEvaluationError, KeyError, json.JSONDecodeError) as exc:
        print(f"[business-evaluation] ERROR: {exc}")
        return 1
    coverage = result["count_coverage"]
    print(
        "[business-evaluation] "
        f"truth={coverage['true_human_entities']:,}; "
        f"estimate={coverage['recommended_estimate']:,}; "
        f"range_coverage={coverage['defensible_range_contains_true_human_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
