"""Diagnose MCT recall gaps without reading the frozen test partition.

This module is a development aid, not a scorer. It consumes only aggregate-safe fields
from person-disjoint development and validation label artifacts and emits aggregate
patterns. Record identifiers and hidden person identifiers are never written.
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


ALLOWED_PARTITIONS = ("development", "validation")
DECISIONS = ("auto_merge", "human_review", "leave_separate")
REQUIRED_COLUMNS = {
    "left_source",
    "right_source",
    "blocking_rules",
    "positive_evidence",
    "conflicts",
    "mct_score",
    "decision",
    "truth_label",
    "partition",
}
SCORE_BANDS = (
    (0.00, 0.40, "0.00-0.40"),
    (0.40, 0.55, "0.40-0.55"),
    (0.55, 0.62, "0.55-0.62 (near review)"),
    (0.62, 0.80, "0.62-0.80 (review)"),
    (0.80, 0.84, "0.80-0.84 (review)"),
    (0.84, 0.88, "0.84-0.88 (near auto)"),
    (0.88, 1.000001, "0.88-1.00 (auto)"),
)


class RecallGapAnalysisError(ValueError):
    """Raised when a recall-gap input violates the isolation contract."""


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


def _load_thresholds(path: Path) -> tuple[float, float]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        thresholds = payload["thresholds"]
        auto = float(thresholds["auto_merge_minimum"])
        review = float(thresholds["human_review_minimum"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RecallGapAnalysisError(f"Unable to load MCT thresholds from {path}: {exc}") from exc
    if not 0.0 <= review < auto <= 1.0:
        raise RecallGapAnalysisError("MCT thresholds must satisfy 0 <= review < auto <= 1")
    return auto, review


def _read_partition(path: Path, expected_partition: str) -> list[dict[str, str]]:
    if expected_partition not in ALLOWED_PARTITIONS:
        raise RecallGapAnalysisError(
            f"Recall-gap analysis permits only {ALLOWED_PARTITIONS}; got {expected_partition!r}"
        )
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            if not REQUIRED_COLUMNS.issubset(fields):
                raise RecallGapAnalysisError(
                    f"{path} is missing columns: {sorted(REQUIRED_COLUMNS - fields)}"
                )
            rows: list[dict[str, str]] = []
            for number, row in enumerate(reader, start=2):
                if row["partition"] != expected_partition:
                    raise RecallGapAnalysisError(
                        f"{path} row {number} belongs to {row['partition']!r}, "
                        f"not {expected_partition!r}"
                    )
                if row["decision"] not in DECISIONS:
                    raise RecallGapAnalysisError(
                        f"{path} row {number} has unknown decision {row['decision']!r}"
                    )
                if row["truth_label"] not in {"match", "non_match"}:
                    raise RecallGapAnalysisError(
                        f"{path} row {number} has unknown truth label {row['truth_label']!r}"
                    )
                try:
                    score = float(row["mct_score"])
                except ValueError as exc:
                    raise RecallGapAnalysisError(
                        f"{path} row {number} has invalid MCT score {row['mct_score']!r}"
                    ) from exc
                if not 0.0 <= score <= 1.0:
                    raise RecallGapAnalysisError(
                        f"{path} row {number} has MCT score outside [0,1]: {score}"
                    )
                rows.append(dict(row))
    except OSError as exc:
        raise RecallGapAnalysisError(f"Unable to read {path}: {exc}") from exc
    if not rows:
        raise RecallGapAnalysisError(f"{path} contains no labelled pairs")
    return rows


def _source_pair(row: Mapping[str, str]) -> str:
    return "+".join(sorted((row["left_source"], row["right_source"])))


def recall_metrics(rows: Iterable[Mapping[str, str]]) -> dict[str, Any]:
    """Summarize true-match recall without calculating misleading overall accuracy."""

    values = list(rows)
    matches = [row for row in values if row["truth_label"] == "match"]
    auto = sum(row["decision"] == "auto_merge" for row in matches)
    review = sum(row["decision"] == "human_review" for row in matches)
    separate = sum(row["decision"] == "leave_separate" for row in matches)
    denominator = len(matches)
    return {
        "candidate_pairs": len(values),
        "true_match_pairs": denominator,
        "auto_merge_true_matches": auto,
        "human_review_true_matches": review,
        "leave_separate_true_matches": separate,
        "auto_recall": auto / denominator if denominator else None,
        "assisted_recall": (auto + review) / denominator if denominator else None,
        "review_recall_gain": review / denominator if denominator else None,
        "residual_recall_gap": separate / denominator if denominator else None,
    }


def _source_rows(rows_by_partition: Mapping[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    groups = {**rows_by_partition, "combined": sum(rows_by_partition.values(), [])}
    for partition, rows in groups.items():
        by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            if row["truth_label"] == "match":
                by_source[_source_pair(row)].append(row)
        unresolved_total = sum(
            row["decision"] != "auto_merge"
            for values in by_source.values()
            for row in values
        )
        for source_pair, values in by_source.items():
            metrics = recall_metrics(values)
            unresolved = metrics["human_review_true_matches"] + metrics["leave_separate_true_matches"]
            unresolved_scores = [
                float(row["mct_score"]) for row in values if row["decision"] != "auto_merge"
            ]
            result.append(
                {
                    "partition": partition,
                    "source_pair": source_pair,
                    **{key: metrics[key] for key in (
                        "true_match_pairs",
                        "auto_merge_true_matches",
                        "human_review_true_matches",
                        "leave_separate_true_matches",
                        "auto_recall",
                        "assisted_recall",
                    )},
                    "unresolved_true_matches": unresolved,
                    "share_of_partition_recall_gap": unresolved / unresolved_total if unresolved_total else 0.0,
                    "mean_unresolved_score": (
                        sum(unresolved_scores) / len(unresolved_scores) if unresolved_scores else None
                    ),
                }
            )
    return sorted(
        result,
        key=lambda row: (
            ("development", "validation", "combined").index(str(row["partition"])),
            -int(row["unresolved_true_matches"]),
            str(row["source_pair"]),
        ),
    )


def _pattern_rows(rows: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    counters: Counter[tuple[str, str, str, str, str]] = Counter()
    scores: dict[tuple[str, str, str, str, str], list[float]] = defaultdict(list)
    for row in rows:
        if row["truth_label"] != "match" or row["decision"] == "auto_merge":
            continue
        key = (
            row["decision"],
            _source_pair(row),
            row["positive_evidence"] or "(none)",
            row["conflicts"] or "(none)",
            row["blocking_rules"] or "(none)",
        )
        counters[key] += 1
        scores[key].append(float(row["mct_score"]))
    result = []
    for key, count in counters.items():
        values = scores[key]
        result.append(
            {
                "decision": key[0],
                "source_pair": key[1],
                "positive_evidence": key[2],
                "conflicts": key[3],
                "blocking_rules": key[4],
                "pair_count": count,
                "mean_score": sum(values) / count,
                "minimum_score": min(values),
                "maximum_score": max(values),
            }
        )
    return sorted(
        result,
        key=lambda row: (
            DECISIONS.index(str(row["decision"])),
            -int(row["pair_count"]),
            str(row["source_pair"]),
        ),
    )


def _score_band(score: float) -> str:
    for lower, upper, label in SCORE_BANDS:
        if lower <= score < upper:
            return label
    raise RecallGapAnalysisError(f"No diagnostic band contains score {score}")


def _score_rows(rows: Iterable[Mapping[str, str]]) -> list[dict[str, Any]]:
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        band = _score_band(float(row["mct_score"]))
        label = "match" if row["truth_label"] == "match" else "non_match"
        counters[band]["pairs"] += 1
        counters[band][label] += 1
    result = []
    for _, _, band in SCORE_BANDS:
        counter = counters[band]
        pairs = counter["pairs"]
        if not pairs:
            continue
        result.append(
            {
                "score_band": band,
                "candidate_pairs": pairs,
                "true_match_pairs": counter["match"],
                "true_non_match_pairs": counter["non_match"],
                "observed_match_rate": counter["match"] / pairs,
            }
        )
    return result


def _write_csv(path: Path, rows: list[Mapping[str, Any]], headers: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _percentage(value: float | None) -> str:
    return "N/A" if value is None else f"{100 * value:.4f}%"


def _report(result: Mapping[str, Any]) -> str:
    combined = result["metrics"]["combined"]
    combined_sources = [
        row for row in result["source_pair_gaps"] if row["partition"] == "combined"
    ]
    top_sources = combined_sources[:8]
    all_patterns = result["unresolved_patterns"]
    review_patterns = [row for row in all_patterns if row["decision"] == "human_review"][:5]
    separate_patterns = [row for row in all_patterns if row["decision"] == "leave_separate"][:5]
    patterns = review_patterns + separate_patterns
    score_rows = result["score_proximity"]
    top_source = top_sources[0] if top_sources else None
    top_review_pattern = review_patterns[0] if review_patterns else None
    top_separate_pattern = separate_patterns[0] if separate_patterns else None

    lines = [
        "# Development/validation recall-gap analysis",
        "",
        "## Isolation contract",
        "",
        "This diagnostic reads only the person-disjoint development and validation labelled sets. "
        "It does not read the frozen test set, alter a score, change the mandatory 0.88/0.62 "
        "thresholds, train a model or emit record/person identifiers.",
        "",
        "## Combined finding",
        "",
        f"Across **{combined['true_match_pairs']:,}** development/validation true candidate matches, "
        f"**{combined['auto_merge_true_matches']:,}** auto-merge and "
        f"**{combined['human_review_true_matches']:,}** enter review. Automatic recall is "
        f"**{_percentage(combined['auto_recall'])}** and assisted recall is "
        f"**{_percentage(combined['assisted_recall'])}**. The review band therefore contains an "
        f"observable **{_percentage(combined['review_recall_gain'])}** recall opportunity, while "
        f"**{combined['leave_separate_true_matches']:,}** true pairs remain below review.",
        "",
        "## Recall gap by source pair",
        "",
        "| Source pair | True matches | Review matches | Separate matches | Auto recall | Assisted recall | Share of gap |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in top_sources:
        lines.append(
            f"| {row['source_pair']} | {row['true_match_pairs']:,} | "
            f"{row['human_review_true_matches']:,} | {row['leave_separate_true_matches']:,} | "
            f"{_percentage(row['auto_recall'])} | {_percentage(row['assisted_recall'])} | "
            f"{_percentage(row['share_of_partition_recall_gap'])} |"
        )
    lines.extend(
        [
            "",
            "## Largest unresolved evidence patterns",
            "",
            "| Decision | Source pair | Evidence | Conflicts | Pairs | Mean score |",
            "|---|---|---|---|---:|---:|",
        ]
    )
    for row in patterns:
        lines.append(
            f"| {row['decision']} | {row['source_pair']} | {row['positive_evidence']} | "
            f"{row['conflicts']} | {row['pair_count']:,} | {row['mean_score']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Score proximity",
            "",
            "These rates are diagnostics, not proposed replacement thresholds. Moving a boundary "
            "would violate the assessment and can create false merges after transitivity.",
            "",
            "| Score band | Pairs | Matches | Non-matches | Observed match rate |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in score_rows:
        lines.append(
            f"| {row['score_band']} | {row['candidate_pairs']:,} | "
            f"{row['true_match_pairs']:,} | {row['true_non_match_pairs']:,} | "
            f"{_percentage(row['observed_match_rate'])} |"
        )
    lines.extend(["", "## Evidence-backed next experiments", ""])
    if top_source:
        lines.append(
            f"1. Start with **{top_source['source_pair']}**, which contributes "
            f"**{_percentage(top_source['share_of_partition_recall_gap'])}** of unresolved "
            "development/validation true pairs. Add source-aware interactions before broad global features."
        )
    if top_review_pattern:
        lines.append(
            f"2. Investigate the leading review pattern—**{top_review_pattern['positive_evidence']}** with "
            f"**{top_review_pattern['conflicts']}**—using conservative name/email/address/temporal similarity. "
            "A similarity feature must require independent corroboration and must be tested against hard negatives."
        )
    if top_separate_pattern:
        lines.append(
            f"3. The leading below-review pattern is **{top_separate_pattern['positive_evidence']}** with "
            f"**{top_separate_pattern['conflicts']}**. Do not promote shared-device evidence alone: "
            "the safe remedy is a new independent identifier or source-specific corroboration because "
            "the same pattern can describe genuinely different people on a shared device."
        )
    lines.extend(
        [
            "4. Treat the review band as the lowest-risk recall opportunity: prioritize high-yield "
            "cluster pairs for adjudication, then use double-reviewed labels in a future development set.",
            "5. Keep Rule 2, Rule 1 and the 0.88/0.62 boundaries unchanged. Any challenger must pass "
            "zero-false-auto-merge validation, hard-negative and post-transitivity cluster gates.",
            "6. Because validation is now being used for error analysis, confirm any future promoted model "
            "on a newly generated, untouched seed rather than repeatedly tuning against the current frozen test.",
            "",
            "Complete aggregates are available in `recall_gap_by_source_pair.csv`, "
            "`unresolved_patterns.csv` and `score_proximity.csv`.",
        ]
    )
    return "\n".join(lines) + "\n"


def analyze_recall_gaps(
    labelled_dir: Path,
    output_dir: Path,
    scoring_config: Path = Path("config/mct_scoring.yaml"),
) -> dict[str, Any]:
    """Create aggregate recall diagnostics from development and validation only."""

    labelled_dir = Path(labelled_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    auto_threshold, review_threshold = _load_thresholds(scoring_config)
    paths = {
        partition: labelled_dir / f"labelled_{partition}_set.csv.gz"
        for partition in ALLOWED_PARTITIONS
    }
    rows_by_partition = {
        partition: _read_partition(path, partition) for partition, path in paths.items()
    }
    combined_rows = sum(rows_by_partition.values(), [])
    metrics = {
        partition: recall_metrics(rows) for partition, rows in rows_by_partition.items()
    }
    metrics["combined"] = recall_metrics(combined_rows)
    source_rows = _source_rows(rows_by_partition)
    pattern_rows = _pattern_rows(combined_rows)
    score_rows = _score_rows(combined_rows)
    result: dict[str, Any] = {
        "phase": "development_validation_recall_gap_analysis",
        "purpose": "feature discovery and review prioritization, not final performance reporting",
        "partitions_read": list(ALLOWED_PARTITIONS),
        "frozen_test_read": False,
        "thresholds_unchanged": {
            "auto_merge_minimum": auto_threshold,
            "human_review_minimum": review_threshold,
        },
        "metrics": metrics,
        "source_pair_gaps": source_rows,
        "unresolved_patterns": pattern_rows,
        "score_proximity": score_rows,
        "privacy": {
            "record_identifiers_emitted": False,
            "hidden_person_identifiers_emitted": False,
            "aggregate_outputs_only": True,
        },
        "inputs": {
            partition: {
                "path": _portable_path(path),
                "sha256": _sha256(path),
                "rows": len(rows_by_partition[partition]),
            }
            for partition, path in paths.items()
        },
    }
    (output_dir / "recall_gap_analysis.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(
        output_dir / "recall_gap_by_source_pair.csv",
        source_rows,
        [
            "partition",
            "source_pair",
            "true_match_pairs",
            "auto_merge_true_matches",
            "human_review_true_matches",
            "leave_separate_true_matches",
            "auto_recall",
            "assisted_recall",
            "unresolved_true_matches",
            "share_of_partition_recall_gap",
            "mean_unresolved_score",
        ],
    )
    _write_csv(
        output_dir / "unresolved_patterns.csv",
        pattern_rows,
        [
            "decision",
            "source_pair",
            "positive_evidence",
            "conflicts",
            "blocking_rules",
            "pair_count",
            "mean_score",
            "minimum_score",
            "maximum_score",
        ],
    )
    _write_csv(
        output_dir / "score_proximity.csv",
        score_rows,
        [
            "score_band",
            "candidate_pairs",
            "true_match_pairs",
            "true_non_match_pairs",
            "observed_match_rate",
        ],
    )
    (output_dir / "recall_gap_analysis.md").write_text(_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze development/validation recall gaps without reading frozen test labels."
    )
    parser.add_argument("--labelled-dir", type=Path, default=Path("outputs/logistic"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/recall-analysis"))
    parser.add_argument(
        "--scoring-config", type=Path, default=Path("config/mct_scoring.yaml")
    )
    args = parser.parse_args()
    try:
        result = analyze_recall_gaps(args.labelled_dir, args.output_dir, args.scoring_config)
    except RecallGapAnalysisError as exc:
        parser.error(str(exc))
    combined = result["metrics"]["combined"]
    print(
        "Recall-gap analysis passed: "
        f"{combined['true_match_pairs']:,} development/validation true matches, "
        f"{combined['human_review_true_matches']:,} in review, "
        f"{combined['leave_separate_true_matches']:,} left separate; frozen test not read."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
