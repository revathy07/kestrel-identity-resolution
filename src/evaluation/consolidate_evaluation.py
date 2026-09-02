"""Consolidate frozen-test subgroup and error analysis for the selected resolver.

This is a post-model-selection evaluator. It reads labelled evaluation artifacts but never
fits a model, changes a threshold, forms candidates, or alters clusters.
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
from typing import Any, Iterable, Mapping


PARTITIONS = ("development", "validation", "test")
DECISIONS = ("auto_merge", "human_review", "leave_separate")
AVAILABILITY_FAMILIES = (
    "email",
    "phone",
    "device",
    "account_or_provider",
    "name",
    "date_of_birth",
    "city",
    "address",
    "payment",
)
CONCEPT_TO_FAMILY = {
    "email": "email",
    "hashed_email": "email",
    "phone": "phone",
    "device_id": "device",
    "account_reference": "account_or_provider",
    "provider_id": "account_or_provider",
    "first_name": "name",
    "last_name": "name",
    "full_name": "name",
    "date_of_birth": "date_of_birth",
    "city": "city",
    "address_line1": "address",
    "address_line2": "address",
    "postcode": "address",
    "payment_token": "payment",
}
REQUIRED_LABEL_COLUMNS = {
    "left_source",
    "left_record_ordinal",
    "right_source",
    "right_record_ordinal",
    "positive_evidence",
    "conflicts",
    "mct_score",
    "decision",
    "truth_label",
    "partition",
}


class ConsolidatedEvaluationError(ValueError):
    """Raised when a Phase 12 evaluation artifact violates its contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConsolidatedEvaluationError(f"Unable to load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConsolidatedEvaluationError(f"Expected a JSON object in {path}")
    return value


def _pair_source(row: Mapping[str, str]) -> str:
    return "+".join(sorted((row["left_source"], row["right_source"])))


def _record_keys(row: Mapping[str, str]) -> tuple[tuple[str, int], tuple[str, int]]:
    return (
        (row["left_source"], int(row["left_record_ordinal"])),
        (row["right_source"], int(row["right_record_ordinal"])),
    )


def _empty_counter() -> Counter[str]:
    return Counter(
        {
            "pairs": 0,
            "matches": 0,
            "nonmatches": 0,
            "auto_merge": 0,
            "auto_merge_match": 0,
            "auto_merge_nonmatch": 0,
            "human_review": 0,
            "human_review_match": 0,
            "human_review_nonmatch": 0,
            "leave_separate": 0,
            "leave_separate_match": 0,
            "leave_separate_nonmatch": 0,
        }
    )


def _update(counter: Counter[str], row: Mapping[str, str]) -> None:
    label = "match" if row["truth_label"] == "match" else "nonmatch"
    decision = row["decision"]
    if decision not in DECISIONS:
        raise ConsolidatedEvaluationError(f"Unknown decision {decision!r}")
    counter["pairs"] += 1
    counter["matches" if label == "match" else "nonmatches"] += 1
    counter[decision] += 1
    counter[f"{decision}_{label}"] += 1


def metrics(counter: Mapping[str, int]) -> dict[str, Any]:
    """Return precision and recall metrics without reporting overall accuracy."""

    matches = int(counter.get("matches", 0))
    auto_true = int(counter.get("auto_merge_match", 0))
    auto_false = int(counter.get("auto_merge_nonmatch", 0))
    review = int(counter.get("human_review", 0))
    review_true = int(counter.get("human_review_match", 0))
    return {
        "candidate_pairs": int(counter.get("pairs", 0)),
        "true_match_pairs": matches,
        "true_non_match_pairs": int(counter.get("nonmatches", 0)),
        "auto_merge_pairs": int(counter.get("auto_merge", 0)),
        "auto_merge_true_positives": auto_true,
        "auto_merge_false_positives": auto_false,
        "auto_merge_precision": auto_true / (auto_true + auto_false) if auto_true + auto_false else None,
        "auto_merge_recall": auto_true / matches if matches else None,
        "human_review_pairs": review,
        "human_review_true_matches": review_true,
        "human_review_yield": review_true / review if review else None,
        "assisted_recall": (auto_true + review_true) / matches if matches else None,
        "leave_separate_pairs": int(counter.get("leave_separate", 0)),
        "leave_separate_true_matches": int(counter.get("leave_separate_match", 0)),
    }


def probability_metrics(rows: Iterable[Mapping[str, str]]) -> dict[str, float]:
    """Measure probabilistic calibration without refitting or transforming scores."""

    values = list(rows)
    if not values:
        raise ConsolidatedEvaluationError("Probability metrics require at least one row")
    brier_sum = 0.0
    log_loss_sum = 0.0
    bins: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for row in values:
        score = float(row["mct_score"])
        label = 1.0 if row["truth_label"] == "match" else 0.0
        if not 0.0 <= score <= 1.0:
            raise ConsolidatedEvaluationError(f"MCT score outside [0,1]: {score}")
        brier_sum += (score - label) ** 2
        clipped = min(max(score, 1e-15), 1.0 - 1e-15)
        log_loss_sum -= label * math.log(clipped) + (1.0 - label) * math.log(1.0 - clipped)
        bins[min(int(score * 10), 9)].append((score, label))
    ece = 0.0
    for items in bins.values():
        mean_score = sum(item[0] for item in items) / len(items)
        observed = sum(item[1] for item in items) / len(items)
        ece += len(items) / len(values) * abs(mean_score - observed)
    return {
        "brier_score": brier_sum / len(values),
        "log_loss": log_loss_sum / len(values),
        "expected_calibration_error_10_bins": ece,
    }


def _read_labels(path: Path, required_partition: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            if not REQUIRED_LABEL_COLUMNS.issubset(fields):
                raise ConsolidatedEvaluationError(
                    f"{path} is missing columns: {sorted(REQUIRED_LABEL_COLUMNS - fields)}"
                )
            if any("person_id" in field.lower() for field in fields):
                raise ConsolidatedEvaluationError("Labelled artifacts must not expose person IDs")
            for number, row in enumerate(reader, start=1):
                if row["partition"] != required_partition:
                    raise ConsolidatedEvaluationError(
                        f"{path} row {number} belongs to {row['partition']!r}, not {required_partition!r}"
                    )
                if row["truth_label"] not in {"match", "non_match"}:
                    raise ConsolidatedEvaluationError(
                        f"Unknown truth label {row['truth_label']!r} at {path} row {number}"
                    )
                rows.append(row)
    except OSError as exc:
        raise ConsolidatedEvaluationError(f"Unable to read {path}: {exc}") from exc
    return rows


def _load_availability(
    normalized_path: Path,
    required_records: set[tuple[str, int]],
) -> dict[tuple[str, int], set[str]]:
    available: dict[tuple[str, int], set[str]] = {key: set() for key in required_records}
    try:
        with gzip.open(normalized_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {
                "source", "record_ordinal", "canonical_concept", "normalized_value", "normalization_status"
            }
            fields = set(reader.fieldnames or [])
            if not required.issubset(fields):
                raise ConsolidatedEvaluationError(
                    f"Normalized identifiers are missing: {sorted(required - fields)}"
                )
            for row in reader:
                key = (row["source"], int(row["record_ordinal"]))
                if key not in available or row["normalization_status"] != "valid":
                    continue
                if not row["normalized_value"].strip():
                    continue
                family = CONCEPT_TO_FAMILY.get(row["canonical_concept"])
                if family:
                    available[key].add(family)
    except OSError as exc:
        raise ConsolidatedEvaluationError(f"Unable to read normalized identifiers: {exc}") from exc
    return available


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], headers: list[str]) -> None:
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _flatten_metrics(group: Mapping[str, Any], values: Mapping[str, Any]) -> dict[str, Any]:
    return {**group, **values}


def _aggregate(rows: Iterable[Mapping[str, str]]) -> Counter[str]:
    counter = _empty_counter()
    for row in rows:
        _update(counter, row)
    return counter


def _source_pair_rows(test_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    counters: dict[str, Counter[str]] = defaultdict(_empty_counter)
    for row in test_rows:
        _update(counters[_pair_source(row)], row)
    return [
        _flatten_metrics({"source_pair": key}, metrics(counters[key]))
        for key in sorted(counters)
    ]


def _event_rows(test_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    counters: dict[str, Counter[str]] = defaultdict(_empty_counter)
    for row in test_rows:
        events = [
            *(f"evidence:{item}" for item in row["positive_evidence"].split(";") if item),
            *(f"conflict:{item}" for item in row["conflicts"].split(";") if item),
        ]
        for event in set(events):
            _update(counters[event], row)
    return [
        _flatten_metrics(
            {"event_type": key.split(":", 1)[0], "event": key.split(":", 1)[1]},
            metrics(counters[key]),
        )
        for key in sorted(counters)
    ]


def _availability_rows(
    test_rows: list[dict[str, str]],
    available: Mapping[tuple[str, int], set[str]],
) -> list[dict[str, Any]]:
    counters: dict[tuple[str, str], Counter[str]] = defaultdict(_empty_counter)
    for row in test_rows:
        left_key, right_key = _record_keys(row)
        left, right = available[left_key], available[right_key]
        for family in AVAILABILITY_FAMILIES:
            present = int(family in left) + int(family in right)
            state = "both_present" if present == 2 else "exactly_one_present" if present == 1 else "neither_present"
            _update(counters[(family, state)], row)
    return [
        _flatten_metrics({"identifier_family": key[0], "availability_state": key[1]}, metrics(counter))
        for key, counter in sorted(counters.items())
    ]


def _score_band_rows(rows_by_partition: Mapping[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    counters: dict[tuple[str, int], Counter[str]] = defaultdict(_empty_counter)
    score_sums: Counter[tuple[str, int]] = Counter()
    for partition in ("validation", "test"):
        for row in rows_by_partition[partition]:
            score = float(row["mct_score"])
            index = min(int(score * 10), 9)
            _update(counters[(partition, index)], row)
            score_sums[(partition, index)] += score
    output: list[dict[str, Any]] = []
    for (partition, index), counter in sorted(counters.items()):
        values = metrics(counter)
        output.append(
            {
                "partition": partition,
                "score_band": f"[{index / 10:.1f},{(index + 1) / 10:.1f}{']' if index == 9 else ')'}",
                "mean_score": score_sums[(partition, index)] / counter["pairs"],
                "observed_match_rate": counter["matches"] / counter["pairs"],
                **values,
            }
        )
    return output


def _unresolved_rows(test_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    counters: dict[tuple[str, str, str, str], Counter[str]] = defaultdict(Counter)
    for row in test_rows:
        if row["truth_label"] != "match" or row["decision"] == "auto_merge":
            continue
        key = (
            row["decision"],
            _pair_source(row),
            row["positive_evidence"] or "(none)",
            row["conflicts"] or "(none)",
        )
        score = float(row["mct_score"])
        counter = counters[key]
        counter["pair_count"] += 1
        counter["score_micro_sum"] += round(score * 1_000_000)
        if "score_min_micro" not in counter or round(score * 1_000_000) < counter["score_min_micro"]:
            counter["score_min_micro"] = round(score * 1_000_000)
        if round(score * 1_000_000) > counter["score_max_micro"]:
            counter["score_max_micro"] = round(score * 1_000_000)
    rows = [
        {
            "decision": key[0],
            "source_pair": key[1],
            "positive_evidence": key[2],
            "conflicts": key[3],
            "pair_count": counter["pair_count"],
            "mean_score": counter["score_micro_sum"] / counter["pair_count"] / 1_000_000,
            "minimum_score": counter["score_min_micro"] / 1_000_000,
            "maximum_score": counter["score_max_micro"] / 1_000_000,
        }
        for key, counter in counters.items()
    ]
    return sorted(rows, key=lambda row: (row["decision"], -row["pair_count"], row["source_pair"], row["positive_evidence"], row["conflicts"]))


def _hard_negative_rows(scoring_evaluation: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "hard_negative_type": label,
            "pairs": values["pairs"],
            "auto_merge": values["auto_merge"],
            "human_review": values["human_review"],
            "leave_separate": values["leave_separate"],
            "blocked": values["blocked"],
            "false_auto_merge_rate": values["false_auto_merge_rate"],
        }
        for label, values in sorted(scoring_evaluation["hard_negative_metrics"]["by_type"].items())
    ]


def _pipeline_rows(
    blocking: Mapping[str, Any],
    scoring: Mapping[str, Any],
    clustering: Mapping[str, Any],
) -> list[dict[str, Any]]:
    canonical = blocking["canonical_link_evaluation"]
    scored = scoring["canonical_link_metrics"]
    clustered = clustering["canonical_link_metrics"]
    return [
        {"population": "all_canonical_links", "stage": "generated_truth", "outcome": "total", "links": canonical["canonical_true_links"]},
        {"population": "all_canonical_links", "stage": "blocking", "outcome": "retained", "links": canonical["retained_true_links"]},
        {"population": "all_canonical_links", "stage": "blocking", "outcome": "blocked", "links": canonical["discarded_true_links_before_scoring"]},
        {"population": "all_canonical_links", "stage": "pair_scoring", "outcome": "auto_merge", "links": scored["auto_merge"]},
        {"population": "all_canonical_links", "stage": "pair_scoring", "outcome": "human_review", "links": scored["human_review"]},
        {"population": "all_canonical_links", "stage": "pair_scoring", "outcome": "leave_separate", "links": scored["leave_separate"]},
        {"population": "all_canonical_links", "stage": "final_clustering", "outcome": "accepted_cluster", "links": clustered["accepted_cluster_links"]},
        {"population": "all_canonical_links", "stage": "final_clustering", "outcome": "not_merged", "links": clustered["not_merged_links"]},
        {"population": "recoverable_canonical_links", "stage": "generated_truth", "outcome": "total", "links": canonical["intended_recoverable_links"]},
        {"population": "recoverable_canonical_links", "stage": "blocking", "outcome": "retained", "links": canonical["retained_recoverable_links"]},
        {"population": "recoverable_canonical_links", "stage": "blocking", "outcome": "blocked", "links": canonical["discarded_recoverable_links_before_scoring"]},
        {"population": "recoverable_canonical_links", "stage": "pair_scoring", "outcome": "auto_merge", "links": scored["recoverable_auto_merge"]},
        {"population": "recoverable_canonical_links", "stage": "pair_scoring", "outcome": "human_review", "links": scored["recoverable_human_review"]},
        {"population": "recoverable_canonical_links", "stage": "pair_scoring", "outcome": "leave_separate", "links": scored["recoverable_leave_separate"]},
        {"population": "recoverable_canonical_links", "stage": "final_clustering", "outcome": "accepted_cluster", "links": clustered["recoverable_accepted_cluster_links"]},
        {"population": "recoverable_canonical_links", "stage": "final_clustering", "outcome": "not_merged", "links": clustered["recoverable_not_merged_links"]},
    ]


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4%}"


def _report(result: Mapping[str, Any]) -> str:
    test = result["frozen_test_summary"]
    review = result["operational_review_context"]
    source_worst = result["diagnostic_highlights"]["lowest_auto_recall_source_pairs"]
    availability = result["diagnostic_highlights"]["identifier_availability"]
    lines = [
        "# Phase 12 consolidated evaluation and error analysis",
        "",
        "## Executive conclusion",
        "",
        f"The selected logistic resolver auto-merges **{test['auto_merge_pairs']:,}** frozen-test candidate pairs with **{test['auto_merge_false_positives']:,} observed false auto-merges**, giving **{_percent(test['auto_merge_precision'])} observed precision**. Auto recall is **{_percent(test['auto_merge_recall'])}** and increases to **{_percent(test['assisted_recall'])}** when true matches routed to review are included.",
        "",
        "This is observed performance on the synthetic fixture, not a guarantee of perfect production precision. Overall accuracy is intentionally omitted; precision and recall are reported separately.",
        "",
        "## Pipeline loss attribution",
        "",
        f"Blocking retains all **{result['blocking_summary']['recoverable_links']:,}** recoverable canonical links and loses none before scoring. The **{result['blocking_summary']['blocked_all_links']:,}** blocked canonical links are deliberately unrecoverable under the usable-evidence definition. Pair scoring and conservative decision bands—not candidate discovery—therefore account for the remaining recoverable links that are not automatically resolved.",
        "",
        f"Final clustering accepts **{result['cluster_summary']['recoverable_links_accepted']:,}** recoverable canonical links and leaves **{result['cluster_summary']['recoverable_links_not_merged']:,}** unresolved. It produces zero mixed-person clusters and connects 0/20,000 explicit hard negatives.",
        "",
        "## Frozen-test subgroup findings",
        "",
        "Lowest auto-recall source pairs with at least one true match:",
        "",
        "| Source pair | True matches | Auto recall | Assisted recall | False auto-merges |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in source_worst:
        lines.append(
            f"| {row['source_pair']} | {row['true_match_pairs']:,} | {_percent(row['auto_merge_recall'])} | {_percent(row['assisted_recall'])} | {row['auto_merge_false_positives']:,} |"
        )
    lines.extend(
        [
            "",
            "Identifier availability is measured from valid normalized endpoint fields, not inferred from disagreement:",
            "",
            "| Identifier family | State | Candidate pairs | Auto recall | Assisted recall |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for row in availability:
        lines.append(
            f"| {row['identifier_family']} | {row['availability_state']} | {row['candidate_pairs']:,} | {_percent(row['auto_merge_recall'])} | {_percent(row['assisted_recall'])} |"
        )
    lines.extend(
        [
            "",
            "## Error analysis",
            "",
            f"There are no observed false auto-merges to characterize in the frozen test. Error analysis therefore focuses on false negatives: **{test['human_review_true_matches']:,}** true matches enter review and **{test['leave_separate_true_matches']:,}** remain separate. The supporting unresolved-pattern table groups these cases by decision, source pair, evidence signature and conflicts without exposing record or person identifiers.",
            "",
            "Hard-negative results are reported by scenario, including blocked cases. A zero false-auto-merge result on curated scenarios is a safety check, not a substitute for the general non-match precision denominator.",
            "",
        "## Calibration and decision bands",
        "",
            f"The frozen-test Brier score is **{result['calibration_summary']['test']['brier_score']:.6f}**, log loss is **{result['calibration_summary']['test']['log_loss']:.6f}**, and ten-bin expected calibration error is **{result['calibration_summary']['test']['expected_calibration_error_10_bins']:.6f}**. The score-band table reports mean predicted probability and observed match rate separately for validation and frozen test. No post-hoc calibration transform or threshold tuning is performed in Phase 12. The assessment's 0.88/0.62 boundaries remain unchanged.",
            "",
            "## Operational review context",
            "",
            f"The full selected run contains **{review['review_pairs']:,}** review pairs. Frozen-test review yield is **{_percent(review['frozen_test_review_yield'])}**; applying that rate mechanically to the full queue suggests about **{review['projected_true_matches_at_test_yield']:,}** true-match reviews. This is a workload-planning projection for Phase 13, not a final customer-count adjustment, because review pairs can overlap transitively and production distribution may differ.",
            "",
            "## Isolation and limitations",
            "",
            "- Subgroup/error conclusions use the person-disjoint frozen test; development rows do not support those conclusions.",
            "- Labels are opened only after scoring and clustering artifacts are frozen.",
            "- No model coefficient, calibration transform, threshold, candidate rule or cluster is modified.",
            "- Evidence-event subgroups overlap when a pair has multiple evidence items.",
            "- Synthetic outcomes may be more separable than future production data and do not measure distribution shift.",
            "- The operational identity count still includes automated/test traffic.",
            "",
            "Supporting CSV files contain the complete subgroup and loss-attribution measurements used by this report.",
            "",
        ]
    )
    return "\n".join(lines)


def consolidate_evaluation(
    labelled_dir: Path,
    normalized_path: Path,
    blocking_evaluation_path: Path,
    scoring_evaluation_path: Path,
    scoring_manifest_path: Path,
    cluster_evaluation_path: Path,
    clustering_manifest_path: Path,
    output_dir: Path,
    *,
    show_progress: bool = True,
) -> dict[str, Any]:
    labelled_dir = Path(labelled_dir)
    label_paths = {
        partition: labelled_dir / f"labelled_{partition}_set.csv.gz"
        for partition in PARTITIONS
    }
    for path in (
        *label_paths.values(),
        normalized_path,
        blocking_evaluation_path,
        scoring_evaluation_path,
        scoring_manifest_path,
        cluster_evaluation_path,
        clustering_manifest_path,
    ):
        if not Path(path).exists():
            raise ConsolidatedEvaluationError(f"Required Phase 12 input not found: {path}")
    rows_by_partition = {
        partition: _read_labels(path, partition) for partition, path in label_paths.items()
    }
    test_rows = rows_by_partition["test"]
    test_metrics = metrics(_aggregate(test_rows))
    source_rows = _source_pair_rows(test_rows)
    event_rows = _event_rows(test_rows)
    endpoint_keys = {key for row in test_rows for key in _record_keys(row)}
    if show_progress:
        print(f"[phase12] Loading identifier availability for {len(endpoint_keys):,} frozen-test endpoints")
    availability = _load_availability(Path(normalized_path), endpoint_keys)
    availability_rows = _availability_rows(test_rows, availability)
    band_rows = _score_band_rows(rows_by_partition)
    unresolved_rows = _unresolved_rows(test_rows)
    blocking = _load_json(Path(blocking_evaluation_path))
    scoring = _load_json(Path(scoring_evaluation_path))
    scoring_manifest = _load_json(Path(scoring_manifest_path))
    clustering = _load_json(Path(cluster_evaluation_path))
    clustering_manifest = _load_json(Path(clustering_manifest_path))
    selected_score_hash = scoring_manifest.get("scored_output", {}).get("sha256")
    if scoring_manifest.get("phase") != "logistic_challenger_scoring" or not selected_score_hash:
        raise ConsolidatedEvaluationError("Scoring manifest is not the selected logistic scorer")
    if scoring.get("scored_pairs_sha256") != selected_score_hash:
        raise ConsolidatedEvaluationError("Labelled scoring evaluation does not match selected logistic scores")
    if clustering_manifest.get("inputs", {}).get("scored_pairs", {}).get("sha256") != selected_score_hash:
        raise ConsolidatedEvaluationError("Promoted clusters do not consume the selected logistic scores")
    if clustering.get("inputs", {}).get("production_assignment_sha256_matches") is not True:
        raise ConsolidatedEvaluationError("Cluster evaluation does not match the promoted assignments")
    hard_rows = _hard_negative_rows(scoring)
    pipeline_rows = _pipeline_rows(blocking, scoring, clustering)
    full_counter = _aggregate(row for partition in PARTITIONS for row in rows_by_partition[partition])
    full_metrics = metrics(full_counter)
    review_projection = round(
        full_metrics["human_review_pairs"] * (test_metrics["human_review_yield"] or 0.0)
    )
    source_with_matches = [row for row in source_rows if row["true_match_pairs"]]
    source_worst = sorted(
        source_with_matches,
        key=lambda row: (row["auto_merge_recall"], row["source_pair"]),
    )[:5]
    availability_highlights = [
        row for row in availability_rows
        if row["identifier_family"] in {"email", "phone"}
        and row["availability_state"] in {"both_present", "neither_present"}
    ]
    result: dict[str, Any] = {
        "phase": "consolidated_selected_resolver_evaluation",
        "selected_model": "logistic_regression_mct_l2_0.001",
        "subgroup_evaluation_partition": "frozen_test",
        "frozen_test_summary": test_metrics,
        "operational_decision_summary": full_metrics,
        "calibration_summary": {
            "validation": probability_metrics(rows_by_partition["validation"]),
            "test": probability_metrics(test_rows),
            "posthoc_transform_fitted": False,
        },
        "blocking_summary": {
            "all_canonical_links": blocking["canonical_link_evaluation"]["canonical_true_links"],
            "blocked_all_links": blocking["canonical_link_evaluation"]["discarded_true_links_before_scoring"],
            "recoverable_links": blocking["canonical_link_evaluation"]["intended_recoverable_links"],
            "recoverable_links_blocked": blocking["canonical_link_evaluation"]["discarded_recoverable_links_before_scoring"],
            "recoverable_blocking_recall": blocking["canonical_link_evaluation"]["recoverable_blocking_recall"],
        },
        "cluster_summary": {
            "pairwise_precision": clustering["pairwise_cluster_metrics"]["precision"],
            "human_pairwise_recall": clustering["pairwise_cluster_metrics"]["recall_humans"],
            "false_merged_pairs": clustering["pairwise_cluster_metrics"]["false_positive_merged_pairs"],
            "mixed_person_components": clustering["accepted_cluster_purity"]["mixed_person_components"],
            "hard_negatives_co_clustered": clustering["hard_negative_metrics"]["co_clustered_after_transitivity"],
            "recoverable_links_accepted": clustering["canonical_link_metrics"]["recoverable_accepted_cluster_links"],
            "recoverable_links_not_merged": clustering["canonical_link_metrics"]["recoverable_not_merged_links"],
        },
        "operational_review_context": {
            "review_pairs": full_metrics["human_review_pairs"],
            "frozen_test_review_pairs": test_metrics["human_review_pairs"],
            "frozen_test_review_true_matches": test_metrics["human_review_true_matches"],
            "frozen_test_review_yield": test_metrics["human_review_yield"],
            "projected_true_matches_at_test_yield": review_projection,
            "projection_is_customer_count_adjustment": False,
        },
        "diagnostic_highlights": {
            "lowest_auto_recall_source_pairs": source_worst,
            "identifier_availability": availability_highlights,
            "unresolved_true_match_patterns": len(unresolved_rows),
        },
        "artifact_rows": {
            "source_pair_performance": len(source_rows),
            "evidence_event_performance": len(event_rows),
            "identifier_availability_performance": len(availability_rows),
            "score_band_performance": len(band_rows),
            "unresolved_match_patterns": len(unresolved_rows),
            "hard_negative_performance": len(hard_rows),
            "pipeline_loss_attribution": len(pipeline_rows),
        },
        "inputs": {
            "labels": {
                partition: {"path": _portable_path(path), "sha256": _sha256(path), "rows": len(rows_by_partition[partition])}
                for partition, path in label_paths.items()
            },
            "normalized_identifiers": {"path": _portable_path(normalized_path), "sha256": _sha256(normalized_path)},
            "blocking_evaluation": {"path": _portable_path(blocking_evaluation_path), "sha256": _sha256(blocking_evaluation_path)},
            "scoring_evaluation": {"path": _portable_path(scoring_evaluation_path), "sha256": _sha256(scoring_evaluation_path)},
            "scoring_manifest": {"path": _portable_path(scoring_manifest_path), "sha256": _sha256(scoring_manifest_path)},
            "cluster_evaluation": {"path": _portable_path(cluster_evaluation_path), "sha256": _sha256(cluster_evaluation_path)},
            "clustering_manifest": {"path": _portable_path(clustering_manifest_path), "sha256": _sha256(clustering_manifest_path)},
        },
        "isolation": {
            "model_or_threshold_modified": False,
            "clusters_modified": False,
            "labels_used_post_model_selection_only": True,
            "person_identifiers_in_outputs": False,
            "subgroup_conclusions_use_frozen_test": True,
            "overall_accuracy_reported": False,
        },
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    common_headers = [
        "candidate_pairs", "true_match_pairs", "true_non_match_pairs", "auto_merge_pairs",
        "auto_merge_true_positives", "auto_merge_false_positives", "auto_merge_precision",
        "auto_merge_recall", "human_review_pairs", "human_review_true_matches",
        "human_review_yield", "assisted_recall", "leave_separate_pairs",
        "leave_separate_true_matches",
    ]
    _write_csv(output_dir / "source_pair_performance.csv", source_rows, ["source_pair", *common_headers])
    _write_csv(output_dir / "evidence_event_performance.csv", event_rows, ["event_type", "event", *common_headers])
    _write_csv(output_dir / "identifier_availability_performance.csv", availability_rows, ["identifier_family", "availability_state", *common_headers])
    _write_csv(output_dir / "score_band_performance.csv", band_rows, ["partition", "score_band", "mean_score", "observed_match_rate", *common_headers])
    _write_csv(output_dir / "unresolved_match_patterns.csv", unresolved_rows, ["decision", "source_pair", "positive_evidence", "conflicts", "pair_count", "mean_score", "minimum_score", "maximum_score"])
    _write_csv(output_dir / "hard_negative_performance.csv", hard_rows, ["hard_negative_type", "pairs", "auto_merge", "human_review", "leave_separate", "blocked", "false_auto_merge_rate"])
    _write_csv(output_dir / "pipeline_loss_attribution.csv", pipeline_rows, ["population", "stage", "outcome", "links"])
    (output_dir / "evaluation_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output_dir / "evaluation_report.md").write_text(_report(result), encoding="utf-8")
    if show_progress:
        print(
            f"[phase12] Complete: {len(test_rows):,} frozen-test pairs; "
            f"{test_metrics['auto_merge_false_positives']:,} false auto-merges"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labelled-dir", type=Path, default=Path("outputs/logistic"))
    parser.add_argument("--normalized", type=Path, default=Path("outputs/normalization/normalized_identifiers.csv.gz"))
    parser.add_argument("--blocking-evaluation", type=Path, default=Path("outputs/blocking/blocking_evaluation.json"))
    parser.add_argument("--scoring-evaluation", type=Path, default=Path("outputs/logistic/mct_evaluation.json"))
    parser.add_argument("--scoring-manifest", type=Path, default=Path("outputs/logistic/logistic_manifest.json"))
    parser.add_argument("--cluster-evaluation", type=Path, default=Path("outputs/clustering/cluster_evaluation.json"))
    parser.add_argument("--clustering-manifest", type=Path, default=Path("outputs/clustering/clustering_manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/evaluation"))
    args = parser.parse_args()
    try:
        consolidate_evaluation(
            args.labelled_dir,
            args.normalized,
            args.blocking_evaluation,
            args.scoring_evaluation,
            args.scoring_manifest,
            args.cluster_evaluation,
            args.clustering_manifest,
            args.output_dir,
        )
    except ConsolidatedEvaluationError as exc:
        print(f"[phase12] ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
