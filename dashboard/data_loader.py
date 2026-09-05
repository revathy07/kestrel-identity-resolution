"""Load and reconcile compact dashboard artifacts without exposing row-level truth."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ARTIFACTS = {
    "business": Path("outputs/business/business_estimate.json"),
    "business_evaluation": Path("outputs/business/business_estimate_evaluation.json"),
    "evaluation": Path("outputs/evaluation/evaluation_summary.json"),
    "model_comparison": Path("outputs/logistic/logistic_comparison.json"),
    "selected_model": Path("outputs/logistic/logistic_model.json"),
    "blocking": Path("outputs/blocking/candidate_manifest.json"),
    "blocking_evaluation": Path("outputs/blocking/blocking_evaluation.json"),
    "clustering": Path("outputs/clustering/clustering_manifest.json"),
    "cluster_evaluation": Path("outputs/clustering/cluster_evaluation.json"),
    "sources": Path("outputs/profiling/source_summary.csv"),
    "cluster_sizes": Path("outputs/clustering/cluster_size_distribution.csv"),
    "source_pairs": Path("outputs/evaluation/source_pair_performance.csv"),
    "traffic": Path("outputs/business/observable_traffic_summary.csv"),
}

MODEL_LABELS = {
    "heuristic_mct": "Heuristic",
    "fellegi_sunter_mct": "Fellegi-Sunter",
    "logistic_regression_mct": "Logistic regression",
}

DECISION_LABELS = {
    "auto_merge": "Auto-merge",
    "human_review": "Human review",
    "leave_separate": "Leave separate",
}


class DashboardDataError(ValueError):
    """Raised when published artifacts cannot support a trustworthy dashboard."""


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardDataError(f"Unable to load dashboard artifact {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DashboardDataError(f"Dashboard JSON artifact is not an object: {path}")
    return value


def _csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise DashboardDataError(f"Unable to load dashboard artifact {path}: {exc}") from exc


def _require(mapping: Mapping[str, Any], path: str, *keys: str) -> None:
    missing = [key for key in keys if key not in mapping]
    if missing:
        raise DashboardDataError(f"{path} is missing required fields: {missing}")


def _integer(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise DashboardDataError(f"{label} must be an integer") from exc


def _float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DashboardDataError(f"{label} must be numeric") from exc


def _model_rows(comparison: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    selected = comparison["selected_model"]
    for key, model in comparison["models"].items():
        validation = model["validation"]
        rows.append(
            {
                "model_key": key,
                "model": MODEL_LABELS.get(key, key),
                "selected": key == selected,
                "precision": float(validation["auto_merge_precision"]),
                "auto_recall": float(validation["auto_merge_recall_within_candidates"]),
                "assisted_recall": float(validation["assisted_recall_within_candidates"]),
                "false_auto_merges": int(validation["auto_merge_false_positives"]),
                "review_pairs": int(validation["human_review_pairs"]),
            }
        )
    return rows


def _validate(snapshot: Mapping[str, Any]) -> None:
    executive = snapshot["executive"]
    source_total = sum(row["records"] for row in snapshot["sources"])
    decision_total = sum(row["pairs"] for row in snapshot["decisions"])
    if source_total != executive["source_records"]:
        raise DashboardDataError("Source rows do not reconcile with the business estimate")
    if snapshot["blocking"]["total_source_records"] != executive["source_records"]:
        raise DashboardDataError("Blocking and business source-record totals disagree")
    if decision_total != snapshot["blocking"]["candidate_pairs"]:
        raise DashboardDataError("MCT decisions do not reconcile with candidate pairs")
    if snapshot["clustering"]["auto_merge_edges"] != next(
        row["pairs"] for row in snapshot["decisions"] if row["decision"] == "Auto-merge"
    ):
        raise DashboardDataError("Cluster input edges do not reconcile with MCT decisions")
    if not executive["range_lower"] <= executive["recommended_customers"] <= executive["range_upper"]:
        raise DashboardDataError("Recommended count is outside the published range")
    coverage = snapshot["business_evaluation"]["count_coverage"]
    if (coverage["defensible_range_lower"], coverage["defensible_range_upper"]) != (
        executive["range_lower"], executive["range_upper"]
    ):
        raise DashboardDataError("Business estimate and hidden-truth evaluation ranges disagree")
    if snapshot["business_evaluation"].get("hidden_identifiers_emitted") is not False:
        raise DashboardDataError("Dashboard refuses evaluations that expose hidden identifiers")
    if snapshot["model_comparison"]["selected_model"] != "logistic_regression_mct":
        raise DashboardDataError("Published selected model is not the expected promoted model")


def load_dashboard_data(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Return a reconciled, presentation-safe snapshot from committed aggregate outputs."""

    root = Path(root)
    missing = [str(relative) for relative in ARTIFACTS.values() if not (root / relative).is_file()]
    if missing:
        raise DashboardDataError(f"Required dashboard artifacts are missing: {missing}")

    business = _json(root / ARTIFACTS["business"])
    business_evaluation = _json(root / ARTIFACTS["business_evaluation"])
    evaluation = _json(root / ARTIFACTS["evaluation"])
    comparison = _json(root / ARTIFACTS["model_comparison"])
    selected_model = _json(root / ARTIFACTS["selected_model"])
    blocking = _json(root / ARTIFACTS["blocking"])
    blocking_evaluation = _json(root / ARTIFACTS["blocking_evaluation"])
    clustering = _json(root / ARTIFACTS["clustering"])
    cluster_evaluation = _json(root / ARTIFACTS["cluster_evaluation"])

    counts = business["customer_count_estimate"]
    workload = business["review_workload"]
    frozen = evaluation["frozen_test_summary"]
    cluster_metrics = evaluation["cluster_summary"]
    _require(
        counts,
        "business.customer_count_estimate",
        "source_records",
        "operational_identities",
        "recommended_candidate_resolvable_count",
        "defensible_range_lower",
        "defensible_range_upper",
    )

    sources = [
        {
            "source": row["source"].replace("_", " ").title(),
            "source_key": row["source"],
            "records": _integer(row["parsed_row_count"], "source parsed_row_count"),
        }
        for row in _csv(root / ARTIFACTS["sources"])
    ]
    decisions = [
        {"decision": DECISION_LABELS[key], "pairs": int(value), "decision_key": key}
        for key, value in clustering["scored_pair_decision_counts"].items()
    ]
    cluster_sizes = [
        {
            "component_size": _integer(row["component_size"], "component_size"),
            "status": row["cluster_status"].replace("_", " ").title(),
            "components": _integer(row["component_count"], "component_count"),
            "records": _integer(row["record_count"], "record_count"),
        }
        for row in _csv(root / ARTIFACTS["cluster_sizes"])
    ]
    source_pairs = []
    for row in _csv(root / ARTIFACTS["source_pairs"]):
        true_matches = _integer(row["true_match_pairs"], "source-pair true matches")
        if true_matches == 0:
            continue
        source_pairs.append(
            {
                "source_pair": row["source_pair"].replace("_", " ").replace("+", " + ").title(),
                "true_matches": true_matches,
                "auto_recall": _float(row["auto_merge_recall"], "source-pair auto recall"),
                "assisted_recall": _float(row["assisted_recall"], "source-pair assisted recall"),
                "false_auto_merges": _integer(
                    row["auto_merge_false_positives"], "source-pair false auto-merges"
                ),
            }
        )
    traffic = [
        {
            "source": row["source"].replace("_", " ").title(),
            "automation": _integer(row["observable_automation_records"], "automation records"),
            "internal_qa": _integer(row["observable_internal_qa_records"], "QA records"),
        }
        for row in _csv(root / ARTIFACTS["traffic"])
    ]

    snapshot: dict[str, Any] = {
        "executive": {
            "source_records": int(counts["source_records"]),
            "operational_identities": int(counts["operational_identities"]),
            "recommended_customers": int(counts["recommended_candidate_resolvable_count"]),
            "range_lower": int(counts["defensible_range_lower"]),
            "range_upper": int(counts["defensible_range_upper"]),
            "review_pairs": int(workload["physical_review_pairs"]),
            "false_auto_merges": int(frozen["auto_merge_false_positives"]),
            "test_auto_precision": float(frozen["auto_merge_precision"]),
            "test_auto_recall": float(frozen["auto_merge_recall"]),
            "test_assisted_recall": float(frozen["assisted_recall"]),
        },
        "sources": sources,
        "decisions": decisions,
        "count_bridge": [
            {"stage": "Source records", "count": int(counts["source_records"]), "order": 1},
            {"stage": "Resolved identities", "count": int(counts["operational_identities"]), "order": 2},
            {"stage": "Upper bound", "count": int(counts["marketing_safe_upper"]), "order": 3},
            {"stage": "Customer estimate", "count": int(counts["recommended_candidate_resolvable_count"]), "order": 4},
        ],
        "models": _model_rows(comparison),
        "model_comparison": comparison,
        "selected_model": selected_model,
        "blocking": {
            "all_possible_pairs": int(blocking["all_possible_unordered_record_pairs"]),
            "candidate_pairs": int(blocking["unique_candidate_pairs"]),
            "candidate_reduction_percentage": float(blocking["candidate_reduction_percentage"]),
            "rule2_values": int(blocking["normalized_rule2_value_count"]),
            "recoverable_links": int(evaluation["blocking_summary"]["recoverable_links"]),
            "recoverable_links_blocked": int(evaluation["blocking_summary"]["recoverable_links_blocked"]),
            "recoverable_blocking_recall": float(evaluation["blocking_summary"]["recoverable_blocking_recall"]),
            "discarded_links": int(
                blocking_evaluation["canonical_link_evaluation"]["discarded_true_links_before_scoring"]
            ),
            "total_source_records": int(blocking["total_source_records"]),
        },
        "clustering": {
            "accepted_merged_components": int(clustering["accepted_merged_component_count"]),
            "accepted_singletons": int(clustering["accepted_singleton_count"]),
            "largest_component": int(clustering["largest_accepted_component_size"]),
            "quarantined_components": int(clustering["quarantined_component_count"]),
            "auto_merge_edges": int(clustering["auto_merge_edges"]),
            "implied_merged_pairs": int(
                cluster_evaluation["pairwise_cluster_metrics"]["predicted_merged_pairs"]
            ),
            "false_merged_pairs": int(cluster_metrics["false_merged_pairs"]),
            "mixed_person_components": int(cluster_metrics["mixed_person_components"]),
            "hard_negatives_co_clustered": int(cluster_metrics["hard_negatives_co_clustered"]),
            "human_pairwise_recall": float(cluster_metrics["human_pairwise_recall"]),
        },
        "cluster_sizes": cluster_sizes,
        "source_pairs": sorted(source_pairs, key=lambda row: row["true_matches"], reverse=True),
        "traffic": traffic,
        "traffic_exclusions": business["observable_traffic_exclusions"],
        "review_workload": workload,
        "business_evaluation": business_evaluation,
        "thresholds": selected_model["thresholds"],
        "meta": {
            "selected_model": comparison["selected_model"],
            "selection_partition": comparison["selection_partition"],
            "frozen_test_used_for_selection": comparison["frozen_test_used_for_selection"],
            "synthetic_evaluation": True,
            "row_level_data_loaded": False,
        },
    }
    _validate(snapshot)
    return snapshot


def score_selected_model(
    model: Mapping[str, Any], selected_events: Iterable[str]
) -> dict[str, Any]:
    """Score an educational event combination with the frozen logistic model."""

    selected = set(selected_events)
    feature_names = list(model["feature_names"])
    base_events = {name for name in feature_names if " & " not in name}
    unknown = selected - base_events
    if unknown:
        raise DashboardDataError(f"Unknown model events: {sorted(unknown)}")
    coefficients = model["coefficients"]
    contributions: list[dict[str, Any]] = []
    logit = float(model["intercept"])
    for feature in feature_names:
        active = feature in selected
        if " & " in feature:
            left, right = feature.split(" & ", 1)
            active = left in selected and right in selected
        if not active:
            continue
        contribution = float(coefficients[feature])
        logit += contribution
        contributions.append({"feature": feature, "contribution": contribution})
    probability = 1.0 / (1.0 + math.exp(-logit)) if logit >= 0 else math.exp(logit) / (1.0 + math.exp(logit))
    score = round(probability, 6)
    auto = float(model["thresholds"]["auto_merge_minimum"])
    review = float(model["thresholds"]["human_review_minimum"])
    decision = "auto_merge" if score >= auto else "human_review" if score >= review else "leave_separate"
    return {
        "score": score,
        "decision": decision,
        "decision_label": DECISION_LABELS[decision],
        "logit": logit,
        "intercept": float(model["intercept"]),
        "contributions": sorted(contributions, key=lambda row: abs(row["contribution"]), reverse=True),
    }
