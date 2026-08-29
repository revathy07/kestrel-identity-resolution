"""Measure Phase 5 blocking recall against isolated synthetic labels.

This module audits candidate discovery after it has completed. It must never be imported
by the production blocker or used to create candidate keys.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sqlite3
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


class BlockingEvaluationError(ValueError):
    """Raised when labelled evaluation inputs are missing or malformed."""


def _ordered_pair(
    source_a: str, record_a: str, source_b: str, record_b: str
) -> tuple[str, str, str, str]:
    left = (str(source_a), str(record_a))
    right = (str(source_b), str(record_b))
    return (*left, *right) if left <= right else (*right, *left)


def _load_candidates(connection: sqlite3.Connection, path: Path) -> int:
    required = {
        "left_source",
        "left_source_record_id",
        "right_source",
        "right_source_record_id",
    }
    connection.execute(
        "CREATE TABLE candidates (left_source TEXT, left_id TEXT, right_source TEXT, right_id TEXT, PRIMARY KEY(left_source, left_id, right_source, right_id)) WITHOUT ROWID"
    )
    physical_rows = 0
    batch: list[tuple[str, str, str, str]] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise BlockingEvaluationError(
                    f"Candidate input is missing columns: {sorted(required - set(reader.fieldnames or []))}"
                )
            for row in reader:
                physical_rows += 1
                pair = _ordered_pair(
                    row["left_source"],
                    row["left_source_record_id"],
                    row["right_source"],
                    row["right_source_record_id"],
                )
                if (pair[0], pair[1]) == (pair[2], pair[3]):
                    continue
                batch.append(pair)
                if len(batch) >= 10_000:
                    connection.executemany("INSERT OR IGNORE INTO candidates VALUES (?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            connection.executemany("INSERT OR IGNORE INTO candidates VALUES (?, ?, ?, ?)", batch)
        connection.commit()
    except OSError as exc:
        raise BlockingEvaluationError(f"Unable to read candidates {path}: {exc}") from exc
    return physical_rows


def _is_candidate(connection: sqlite3.Connection, pair: tuple[str, str, str, str]) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM candidates WHERE left_source=? AND left_id=? AND right_source=? AND right_id=?",
            pair,
        ).fetchone()
        is not None
    )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _measure_canonical(
    connection: sqlite3.Connection, path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    total = retained = recoverable = recoverable_retained = 0
    by_mode: dict[str, Counter[str]] = defaultdict(Counter)
    by_source: dict[str, Counter[str]] = defaultdict(Counter)
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    pair = _ordered_pair(
                        item["source_system_a"],
                        item["source_record_id_a"],
                        item["source_system_b"],
                        item["source_record_id_b"],
                    )
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise BlockingEvaluationError(f"Invalid canonical link at line {line_number}: {exc}") from exc
                found = _is_candidate(connection, pair)
                intended = bool(item.get("intended_recoverability"))
                modes = item.get("evidence_modes") or [item.get("evidence_mode", "unspecified")]
                source_pair = "+".join(sorted((str(item["source_system_a"]), str(item["source_system_b"]))))
                total += 1
                retained += int(found)
                recoverable += int(intended)
                recoverable_retained += int(intended and found)
                for label, counter in ((source_pair, by_source[source_pair]),):
                    del label
                    counter["total"] += 1
                    counter["retained"] += int(found)
                    counter["recoverable"] += int(intended)
                    counter["recoverable_retained"] += int(intended and found)
                for mode in modes:
                    counter = by_mode[str(mode)]
                    counter["total"] += 1
                    counter["retained"] += int(found)
                    counter["recoverable"] += int(intended)
                    counter["recoverable_retained"] += int(intended and found)
    except OSError as exc:
        raise BlockingEvaluationError(f"Unable to read canonical links {path}: {exc}") from exc

    def rows(counters: dict[str, Counter[str]], label_name: str) -> list[dict[str, Any]]:
        result = []
        for label, counts in sorted(counters.items()):
            result.append(
                {
                    label_name: label,
                    "true_links": counts["total"],
                    "retained_links": counts["retained"],
                    "discarded_links": counts["total"] - counts["retained"],
                    "blocking_recall": _rate(counts["retained"], counts["total"]),
                    "intended_recoverable_links": counts["recoverable"],
                    "retained_recoverable_links": counts["recoverable_retained"],
                    "recoverable_blocking_recall": _rate(counts["recoverable_retained"], counts["recoverable"]),
                }
            )
        return result

    summary = {
        "canonical_true_links": total,
        "retained_true_links": retained,
        "discarded_true_links_before_scoring": total - retained,
        "overall_blocking_recall": _rate(retained, total),
        "intended_recoverable_links": recoverable,
        "retained_recoverable_links": recoverable_retained,
        "discarded_recoverable_links_before_scoring": recoverable - recoverable_retained,
        "recoverable_blocking_recall": _rate(recoverable_retained, recoverable),
        "known_unrecoverable_links": total - recoverable,
        "labelled_usable_exact_evidence_baseline_recall": _rate(recoverable, total),
    }
    return summary, rows(by_mode, "evidence_mode"), rows(by_source, "source_pair")


def _measure_hard_negatives(connection: sqlite3.Connection, path: Path) -> dict[str, Any]:
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BlockingEvaluationError(f"Unable to read hard-negative labels {path}: {exc}") from exc
    if not isinstance(items, list):
        raise BlockingEvaluationError("Hard-negative labels must be a JSON list")
    total = retained = 0
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    for item in items:
        refs = item.get("source_records", []) if isinstance(item, dict) else []
        if len(refs) != 2:
            raise BlockingEvaluationError("Each hard-negative label must contain two source records")
        pair = _ordered_pair(refs[0]["system"], refs[0]["record_id"], refs[1]["system"], refs[1]["record_id"])
        found = _is_candidate(connection, pair)
        label = str(item.get("type", "unspecified"))
        total += 1
        retained += int(found)
        by_type[label]["total"] += 1
        by_type[label]["retained"] += int(found)
    return {
        "explicit_hard_negative_pairs": total,
        "retained_as_candidates": retained,
        "candidate_coverage": _rate(retained, total),
        "by_type": {
            label: {
                "pairs": counts["total"],
                "retained_as_candidates": counts["retained"],
                "candidate_coverage": _rate(counts["retained"], counts["total"]),
            }
            for label, counts in sorted(by_type.items())
        },
    }


def _table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    header_list = list(headers)
    lines = ["| " + " | ".join(header_list) + " |", "|" + "|".join("---" for _ in header_list) + "|"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _report(result: dict[str, Any]) -> str:
    summary = result["canonical_link_evaluation"]
    hard = result["hard_negative_evaluation"]
    return "\n".join(
        [
            "# Phase 5 blocking evaluation",
            "",
            "## Main result",
            "",
            f"Blocking retained **{summary['retained_true_links']:,} / {summary['canonical_true_links']:,}** canonical true links ({summary['overall_blocking_recall']:.4%}).",
            f"It discarded **{summary['discarded_true_links_before_scoring']:,}** known true links before scoring.",
            f"Among links labelled recoverable from usable evidence, it retained **{summary['retained_recoverable_links']:,} / {summary['intended_recoverable_links']:,}** ({summary['recoverable_blocking_recall']:.4%}).",
            f"The labels identify **{summary['known_unrecoverable_links']:,}** zero-usable-exact-evidence links. Using only links labelled recoverable would give a {summary['labelled_usable_exact_evidence_baseline_recall']:.4%} overall baseline; discovery-only proxies can still retrieve some of the remainder.",
            "",
            "## By evidence mode",
            "",
            _table(
                ["Mode", "True links", "Retained", "Discarded", "Recall"],
                [
                    [row["evidence_mode"], row["true_links"], row["retained_links"], row["discarded_links"], f"{row['blocking_recall']:.4%}"]
                    for row in result["by_evidence_mode"]
                ],
            ),
            "",
            "## Hard-negative candidate coverage",
            "",
            f"**{hard['retained_as_candidates']:,} / {hard['explicit_hard_negative_pairs']:,}** explicit hard negatives are retained for later scoring ({hard['candidate_coverage']:.4%}). Retention here is desirable coverage, not a false match; no match decision exists yet.",
            "",
            "## Isolation statement",
            "",
            "This report is produced after candidate generation. Synthetic labels were used only by this evaluator and did not create, remove, score, or rank candidates.",
            "",
        ]
    )


def evaluate_blocking(
    candidate_path: Path,
    canonical_links_path: Path,
    hard_negatives_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    candidate_path = Path(candidate_path)
    canonical_links_path = Path(canonical_links_path)
    hard_negatives_path = Path(hard_negatives_path)
    output_dir = Path(output_dir)
    for path in (candidate_path, canonical_links_path, hard_negatives_path):
        if not path.exists():
            raise BlockingEvaluationError(f"Required evaluation input not found: {path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_directory = Path(tempfile.mkdtemp(prefix="kestrel-blocking-eval-"))
    database_path = temp_directory / "blocking_evaluation.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        candidate_rows = _load_candidates(connection, candidate_path)
        canonical, by_mode, by_source = _measure_canonical(connection, canonical_links_path)
        hard = _measure_hard_negatives(connection, hard_negatives_path)
    finally:
        connection.close()
        try:
            database_path.unlink(missing_ok=True)
            temp_directory.rmdir()
        except OSError:
            pass
    result = {
        "phase": "blocking_evaluation",
        "candidate_physical_pair_rows": candidate_rows,
        "canonical_link_evaluation": canonical,
        "by_evidence_mode": by_mode,
        "by_source_pair": by_source,
        "hard_negative_evaluation": hard,
        "isolation": {
            "labels_used_after_candidate_generation_only": True,
            "labels_used_as_blocking_features": False,
            "match_scores_calculated": False,
            "match_decisions_made": False,
            "clusters_formed": False,
        },
    }
    (output_dir / "blocking_evaluation.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output_dir / "blocking_evaluation.md").write_text(_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-path", type=Path, default=Path("outputs/blocking/candidate_pairs.csv.gz"))
    parser.add_argument("--canonical-links", type=Path, default=Path("data/generated/hidden/canonical_duplicate_links.jsonl"))
    parser.add_argument("--hard-negatives", type=Path, default=Path("data/generated/hard_negatives.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/blocking"))
    args = parser.parse_args()
    try:
        result = evaluate_blocking(args.candidate_path, args.canonical_links, args.hard_negatives, args.output_dir)
    except BlockingEvaluationError as exc:
        print(f"[blocking-evaluation] ERROR: {exc}")
        return 1
    summary = result["canonical_link_evaluation"]
    print(
        f"[blocking-evaluation] Retained {summary['retained_true_links']:,}/{summary['canonical_true_links']:,} "
        f"canonical true links; discarded {summary['discarded_true_links_before_scoring']:,}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
