"""Score Phase 5 candidate pairs with the explainable MCT model.

This production-style command reads normalized identifiers, candidate pairs, and the
post-normalization Rule 2 registry. It does not read evaluation labels and does not cluster.
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

from src.scoring.rules import DEFAULT_RULES, ScoringError, ScoringRecord, load_scoring_rules, score_pair


SCORER_VERSION = 1
SCORE_COLUMNS = [
    "left_source",
    "left_record_ordinal",
    "left_source_record_id",
    "right_source",
    "right_record_ordinal",
    "right_source_record_id",
    "blocking_rules",
    "positive_evidence",
    "evidence_family_count",
    "conflicts",
    "positive_score",
    "conflict_penalty",
    "mct_score",
    "decision",
]
REQUIRED_CANDIDATE_COLUMNS = {
    "left_source",
    "left_record_ordinal",
    "left_source_record_id",
    "right_source",
    "right_record_ordinal",
    "right_source_record_id",
    "blocking_rules",
}


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


def _candidate_record_keys(path: Path) -> tuple[set[tuple[str, int]], int]:
    keys: set[tuple[str, int]] = set()
    rows = 0
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not REQUIRED_CANDIDATE_COLUMNS.issubset(reader.fieldnames):
                raise ScoringError(
                    f"Candidate input is missing columns: {sorted(REQUIRED_CANDIDATE_COLUMNS - set(reader.fieldnames or []))}"
                )
            for row in reader:
                rows += 1
                try:
                    keys.add((row["left_source"], int(row["left_record_ordinal"])))
                    keys.add((row["right_source"], int(row["right_record_ordinal"])))
                except (TypeError, ValueError) as exc:
                    raise ScoringError(f"Invalid physical record ordinal in candidate row {rows}") from exc
    except OSError as exc:
        raise ScoringError(f"Unable to read candidate input {path}: {exc}") from exc
    return keys, rows


def _load_records(
    path: Path, needed: set[tuple[str, int]]
) -> dict[tuple[str, int], ScoringRecord]:
    required = {
        "source",
        "record_ordinal",
        "source_record_id",
        "canonical_concept",
        "normalized_value",
        "normalization_status",
        "evidence_role",
    }
    records: dict[tuple[str, int], ScoringRecord] = {}
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ScoringError(
                    f"Normalized input is missing columns: {sorted(required - set(reader.fieldnames or []))}"
                )
            for row in reader:
                key = (row["source"], int(row["record_ordinal"]))
                if key not in needed:
                    continue
                record = records.get(key)
                if record is None:
                    record = ScoringRecord(key[0], key[1], row["source_record_id"], defaultdict(set), defaultdict(set))
                    records[key] = record
                elif record.source_record_id != row["source_record_id"]:
                    raise ScoringError(f"Conflicting source record IDs for {key}")
                if row["normalization_status"] == "valid" and row["normalized_value"]:
                    concept, value = row["canonical_concept"], row["normalized_value"]
                    record.values[concept].add(value)
                    record.roles[(concept, value)].add(row["evidence_role"])
    except (OSError, ValueError) as exc:
        if isinstance(exc, ScoringError):
            raise
        raise ScoringError(f"Unable to read normalized input {path}: {exc}") from exc
    missing = needed - set(records)
    if missing:
        sample = sorted(missing)[:5]
        raise ScoringError(f"Normalized input is missing {len(missing):,} candidate records; sample={sample}")
    return records


def _load_worthless(path: Path) -> tuple[set[tuple[str, str]], int]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload["threshold"]) != 40 or not isinstance(payload["values"], list):
            raise ValueError("invalid Rule 2 structure or threshold")
        values = {
            (str(item["attribute_concept"]), str(item["normalized_value"]))
            for item in payload["values"]
            if item.get("rule2_status") == "worthless" and int(item["global_frequency"]) > 40
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ScoringError(f"Unable to load normalized Rule 2 registry {path}: {exc}") from exc
    if len(values) != len(payload["values"]):
        raise ScoringError("Every normalized Rule 2 registry entry must be unique and above 40")
    return values, int(payload["threshold"])


def _open_deterministic_gzip_csv(path: Path) -> tuple[Any, Any, csv.DictWriter]:
    binary = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=SCORE_COLUMNS)
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


def _report(manifest: Mapping[str, Any], decisions: list[dict[str, Any]], features: list[dict[str, Any]]) -> str:
    return "\n".join(
        [
            "# Phase 6 MCT scoring report",
            "",
            "## Outcome",
            "",
            f"All **{manifest['candidate_pairs_scored']:,}** Phase 5 candidates received an explainable MCT score from 0 to 1.",
            "",
            _table(
                ["Decision", "MCT band", "Pairs", "Percentage"],
                [[row["decision"], row["mct_band"], f"{row['pair_count']:,}", f"{row['percentage']:.4f}%"] for row in decisions],
            ),
            "",
            "The bands are fixed by the assessment: at least 0.88 auto-merges, 0.62–0.88 enters human review, and below 0.62 remains separate.",
            "",
            "## Scoring method",
            "",
            "The strongest feature in each correlated evidence family is retained. Independent family strengths are combined with noisy-OR; documented conflict penalties are then subtracted and safety caps are applied. This prevents exact email, its skeleton and its SHA-256 bridge from being counted as three independent identifiers.",
            "",
            "## Feature coverage",
            "",
            _table(
                ["Feature", "Candidate pairs"],
                [[row["feature"], f"{row['pair_count']:,}"] for row in features],
            ),
            "",
            "## Rule 2 and isolation",
            "",
            f"The scorer loaded **{manifest['rule2_value_count']:,}** normalized values occurring on more than 40 physical records. They contribute neither positive nor negative weight.",
            "The production scorer reads no evaluation label. Pair labels are opened only by the separate Phase 6 evaluator after this output exists.",
            "",
            "## Phase boundary",
            "",
            "Phase 6 assigns pair decision bands but does not merge transitively or form clusters. Rule 1's 12-record cluster cap belongs to the next clustering phase.",
            "",
        ]
    )


def score_candidates(
    normalized_path: Path,
    candidate_path: Path,
    rule2_registry_path: Path,
    output_dir: Path,
    *,
    rules_path: Path = DEFAULT_RULES,
    show_progress: bool = True,
) -> dict[str, Any]:
    normalized_path = Path(normalized_path)
    candidate_path = Path(candidate_path)
    rule2_registry_path = Path(rule2_registry_path)
    output_dir = Path(output_dir)
    rules_path = Path(rules_path)
    for path in (normalized_path, candidate_path, rule2_registry_path, rules_path):
        if not path.exists():
            raise ScoringError(f"Required scoring input not found: {path}")
    rules = load_scoring_rules(rules_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    if show_progress:
        print("[scoring] Reading candidate record identities...")
    needed, candidate_count = _candidate_record_keys(candidate_path)
    if show_progress:
        print(f"[scoring] Loading normalized values for {len(needed):,} candidate records...")
    records = _load_records(normalized_path, needed)
    worthless, threshold = _load_worthless(rule2_registry_path)

    score_path = output_dir / "scored_candidate_pairs.csv.gz"
    binary, text_handle, writer = _open_deterministic_gzip_csv(score_path)
    decisions: Counter[str] = Counter()
    feature_counts: Counter[str] = Counter()
    conflict_counts: Counter[str] = Counter()
    family_counts: Counter[int] = Counter()
    score_sum = 0.0
    scored = 0
    try:
        with gzip.open(candidate_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                left_key = (row["left_source"], int(row["left_record_ordinal"]))
                right_key = (row["right_source"], int(row["right_record_ordinal"]))
                left, right = records[left_key], records[right_key]
                if left.source_record_id != row["left_source_record_id"] or right.source_record_id != row["right_source_record_id"]:
                    raise ScoringError(f"Candidate-to-normalized record ID mismatch at pair {scored + 1}")
                result = score_pair(left, right, worthless, rules)
                writer.writerow(
                    {
                        "left_source": left.source,
                        "left_record_ordinal": left.ordinal,
                        "left_source_record_id": left.source_record_id,
                        "right_source": right.source,
                        "right_record_ordinal": right.ordinal,
                        "right_source_record_id": right.source_record_id,
                        "blocking_rules": row["blocking_rules"],
                        "positive_evidence": ";".join(result.evidence),
                        "evidence_family_count": len(result.family_strengths),
                        "conflicts": ";".join(result.conflicts),
                        "positive_score": f"{result.positive_score:.6f}",
                        "conflict_penalty": f"{result.conflict_penalty:.6f}",
                        "mct_score": f"{result.mct_score:.6f}",
                        "decision": result.decision,
                    }
                )
                decisions[result.decision] += 1
                feature_counts.update(result.evidence)
                conflict_counts.update(result.conflicts)
                family_counts[len(result.family_strengths)] += 1
                score_sum += result.mct_score
                scored += 1
    finally:
        text_handle.close()
        binary.close()
    if scored != candidate_count:
        raise ScoringError(f"Scored {scored:,} pairs but candidate input contains {candidate_count:,}")

    auto = float(rules["thresholds"]["auto_merge_minimum"])
    review = float(rules["thresholds"]["human_review_minimum"])
    decision_rows = [
        {
            "decision": decision,
            "mct_band": f">={auto:.2f}" if decision == "auto_merge" else f">={review:.2f} and <{auto:.2f}" if decision == "human_review" else f"<{review:.2f}",
            "pair_count": decisions[decision],
            "percentage": round(100 * decisions[decision] / scored, 6) if scored else 0.0,
        }
        for decision in ("auto_merge", "human_review", "leave_separate")
    ]
    feature_rows = [
        {"feature": feature, "pair_count": count, "percentage": round(100 * count / scored, 6) if scored else 0.0}
        for feature, count in sorted(feature_counts.items())
    ]
    conflict_rows = [
        {"conflict": conflict, "pair_count": count, "percentage": round(100 * count / scored, 6) if scored else 0.0}
        for conflict, count in sorted(conflict_counts.items())
    ]
    _write_csv(output_dir / "mct_decision_summary.csv", decision_rows, ["decision", "mct_band", "pair_count", "percentage"])
    _write_csv(output_dir / "mct_feature_summary.csv", feature_rows, ["feature", "pair_count", "percentage"])
    _write_csv(output_dir / "mct_conflict_summary.csv", conflict_rows, ["conflict", "pair_count", "percentage"])
    manifest: dict[str, Any] = {
        "phase": "mct_pair_scoring",
        "scorer_version": SCORER_VERSION,
        "candidate_pairs_scored": scored,
        "candidate_records_loaded": len(records),
        "rule2_threshold": threshold,
        "rule2_value_count": len(worthless),
        "thresholds": rules["thresholds"],
        "decision_counts": dict(decisions),
        "mean_mct_score": round(score_sum / scored, 6) if scored else 0.0,
        "evidence_family_count_distribution": {str(key): value for key, value in sorted(family_counts.items())},
        "inputs": {
            "normalized": {"path": _portable_path(normalized_path), "sha256": _sha256(normalized_path)},
            "candidates": {"path": _portable_path(candidate_path), "sha256": _sha256(candidate_path)},
            "rule2_registry": {"path": _portable_path(rule2_registry_path), "sha256": _sha256(rule2_registry_path)},
            "configuration": {"path": _portable_path(rules_path), "sha256": _sha256(rules_path)},
        },
        "scored_output": {
            "path": score_path.name,
            "compression": "gzip",
            "rows": scored,
            "size_bytes": score_path.stat().st_size,
            "sha256": _sha256(score_path),
        },
        "phase_boundaries": {
            "candidate_pairs_scored": True,
            "mct_decision_bands_assigned": True,
            "evaluation_labels_read": False,
            "transitive_merging_performed": False,
            "clusters_formed": False,
            "cluster_size_cap_applied": False,
        },
    }
    (output_dir / "mct_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output_dir / "mct_scoring_report.md").write_text(_report(manifest, decision_rows, feature_rows), encoding="utf-8")
    if show_progress:
        print(
            f"[scoring] Complete: {scored:,} pairs; {decisions['auto_merge']:,} auto-merge, "
            f"{decisions['human_review']:,} review, {decisions['leave_separate']:,} separate"
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized-path", type=Path, default=Path("outputs/normalization/normalized_identifiers.csv.gz"))
    parser.add_argument("--candidate-path", type=Path, default=Path("outputs/blocking/candidate_pairs.csv.gz"))
    parser.add_argument("--rule2-registry", type=Path, default=Path("outputs/blocking/normalized_rule2_registry.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/scoring"))
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()
    try:
        score_candidates(
            args.normalized_path,
            args.candidate_path,
            args.rule2_registry,
            args.output_dir,
            rules_path=args.rules,
        )
    except ScoringError as exc:
        print(f"[scoring] ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
