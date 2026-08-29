"""Evaluate Phase 6 MCT scores against isolated synthetic labels.

Development mode exposes only the deterministic development partition. Final mode releases
the frozen test and audit partitions and writes a labelled test-set artifact without person
identifiers. Nothing in this module is imported by production scoring.
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _partition(payload: str) -> str:
    bucket = int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12], 16) % 100
    return "development" if bucket < 50 else "test" if bucket < 80 else "audit"


def _physical_payload(row: Mapping[str, str]) -> str:
    return "\x1f".join(
        (
            row["left_source"],
            row["left_record_ordinal"],
            row["left_source_record_id"],
            row["right_source"],
            row["right_record_ordinal"],
            row["right_source_record_id"],
        )
    )


def _logical_pair(
    source_a: str, record_a: str, source_b: str, record_b: str
) -> tuple[str, str, str, str]:
    left, right = (str(source_a), str(record_a)), (str(source_b), str(record_b))
    return (*left, *right) if left <= right else (*right, *left)


def _logical_payload(pair: tuple[str, str, str, str]) -> str:
    return "\x1f".join(pair)


def _load_truth(path: Path) -> dict[tuple[str, int], tuple[str, str, str]]:
    counters: Counter[str] = Counter()
    truth: dict[tuple[str, int], tuple[str, str, str]] = {}
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
                truth[(source, counters[source])] = (
                    row["record_id"],
                    row["person_id"],
                    row["entity_type"],
                )
    except OSError as exc:
        raise ScoringEvaluationError(f"Unable to read truth map {path}: {exc}") from exc
    return truth


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


def _open_test_set(path: Path) -> tuple[Any, Any, csv.DictWriter]:
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
    selected_partitions: set[str],
) -> dict[str, Any]:
    overall: Counter[str] = Counter()
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    for pair, label in hard_pairs.items():
        if _partition(_logical_payload(pair)) not in selected_partitions:
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
    for name, metrics in partitions.items():
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
        "Candidate pairs are assigned by a stable SHA-256 hash to 50% development, 30% frozen test and 20% audit partitions. This preserves the natural candidate prevalence without outcome-based resampling. Person identifiers are used only to create the match/non-match label and are not written to the labelled artifact.",
        "",
        "## Isolation",
        "",
        "The MCT configuration and scored-pair file existed before labels were opened. This evaluator cannot alter production scores or decisions. Final mode releases the previously hidden test and audit metrics; development mode exposes only development metrics.",
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
) -> dict[str, Any]:
    if scope not in {"development", "final"}:
        raise ScoringEvaluationError("Evaluation scope must be 'development' or 'final'")
    scored_path = Path(scored_path)
    scoring_manifest_path = Path(scoring_manifest_path)
    truth_map_path = Path(truth_map_path)
    canonical_links_path = Path(canonical_links_path)
    hard_negatives_path = Path(hard_negatives_path)
    output_dir = Path(output_dir)
    for path in (scored_path, scoring_manifest_path, truth_map_path, canonical_links_path, hard_negatives_path):
        if not path.exists():
            raise ScoringEvaluationError(f"Required scoring-evaluation input not found: {path}")
    try:
        scoring_manifest = json.loads(scoring_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoringEvaluationError(f"Unable to read scoring manifest: {exc}") from exc
    if scoring_manifest.get("phase_boundaries", {}).get("evaluation_labels_read") is not False:
        raise ScoringEvaluationError("Scoring manifest does not prove label isolation")

    truth = _load_truth(truth_map_path)
    hard_pairs, _hard_types = _load_hard_negatives(hard_negatives_path)
    selected_partitions = {"development"} if scope == "development" else {"development", "test", "audit"}
    pair_counters: dict[str, Counter[str]] = defaultdict(Counter)
    false_auto_features: Counter[str] = Counter()
    false_auto_conflicts: Counter[str] = Counter()
    logical_scores: dict[tuple[str, str, str, str], tuple[float, str]] = {}
    test_path = output_dir / "labelled_test_set.csv.gz"
    output_dir.mkdir(parents=True, exist_ok=True)
    binary = text_handle = writer = None
    if scope == "final":
        binary, text_handle, writer = _open_test_set(test_path)
    try:
        with gzip.open(scored_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = set(TEST_COLUMNS) - {"truth_label", "hard_negative_type", "partition"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ScoringEvaluationError(
                    f"Scored input is missing columns: {sorted(required - set(reader.fieldnames or []))}"
                )
            for row_number, row in enumerate(reader, start=1):
                try:
                    left_key = (row["left_source"], int(row["left_record_ordinal"]))
                    right_key = (row["right_source"], int(row["right_record_ordinal"]))
                    left_truth, right_truth = truth[left_key], truth[right_key]
                except (KeyError, TypeError, ValueError) as exc:
                    raise ScoringEvaluationError(f"Unable to label scored row {row_number}: {exc}") from exc
                if left_truth[0] != row["left_source_record_id"] or right_truth[0] != row["right_source_record_id"]:
                    raise ScoringEvaluationError(f"Truth record ID mismatch at scored row {row_number}")
                label = "match" if left_truth[1] == right_truth[1] else "non_match"
                decision = row["decision"]
                if decision not in DECISIONS:
                    raise ScoringEvaluationError(f"Unknown MCT decision {decision!r} at row {row_number}")
                partition = _partition(_physical_payload(row))
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
                if writer is not None and partition == "test":
                    writer.writerow(
                        {
                            **{column: row[column] for column in TEST_COLUMNS if column in row},
                            "truth_label": label,
                            "hard_negative_type": hard_pairs.get(logical, ""),
                            "partition": partition,
                        }
                    )
    finally:
        if text_handle is not None:
            text_handle.close()
        if binary is not None:
            binary.close()

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
                partition = _partition(_logical_payload(logical))
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

    pair_metrics = {partition: _pair_metrics(pair_counters[partition]) for partition in sorted(selected_partitions)}
    result: dict[str, Any] = {
        "phase": "mct_scoring_evaluation",
        "scope": scope,
        "partition_policy": {
            "method": "SHA-256 of stable pair identity modulo 100",
            "development": "0-49 (50%)",
            "test": "50-79 (30%)",
            "audit": "80-99 (20%)",
            "outcome_stratification_used": False,
        },
        "scoring_configuration_sha256": scoring_manifest["inputs"]["configuration"]["sha256"],
        "scored_pairs_sha256": _sha256(scored_path),
        "pair_metrics_by_partition": pair_metrics,
        "canonical_link_metrics": _canonical_metrics(canonical_counters),
        "hard_negative_metrics": _hard_negative_metrics(hard_pairs, logical_scores, selected_partitions),
        "false_auto_merge_diagnostics": {
            "positive_features": dict(false_auto_features.most_common()),
            "conflicts": dict(false_auto_conflicts.most_common()),
        },
        "labelled_test_set": None,
        "isolation": {
            "scores_created_before_labels_opened": True,
            "labels_used_as_scoring_features": False,
            "overall_accuracy_reported": False,
            "clusters_formed": False,
        },
    }
    if scope == "final":
        result["labelled_test_set"] = {
            "path": test_path.name,
            "compression": "gzip",
            "rows": pair_metrics["test"]["candidate_pairs"],
            "size_bytes": test_path.stat().st_size,
            "sha256": _sha256(test_path),
            "person_identifiers_included": False,
        }
    prefix = "mct_development_evaluation" if scope == "development" else "mct_evaluation"
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
    parser.add_argument("--scope", choices=("development", "final"), default="development")
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
