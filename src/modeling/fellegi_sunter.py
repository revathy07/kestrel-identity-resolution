"""Estimate and apply a sparse Fellegi-Sunter-style MCT challenger.

Training reads only the person-disjoint development labels. Application reads a frozen
model and the truth-free Phase 6 pair evidence; it never opens an evaluation label.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


FS_VERSION = 1
AUTO_MERGE_MINIMUM = 0.88
HUMAN_REVIEW_MINIMUM = 0.62
DEFAULT_ALPHA = 0.5
REQUIRED_TRAINING_COLUMNS = {
    "positive_evidence",
    "conflicts",
    "truth_label",
    "partition",
}
REQUIRED_SCORING_COLUMNS = {
    "left_source",
    "left_record_ordinal",
    "left_source_record_id",
    "right_source",
    "right_record_ordinal",
    "right_source_record_id",
    "blocking_rules",
    "positive_evidence",
    "conflicts",
}
FS_SCORE_COLUMNS = [
    "left_source",
    "left_record_ordinal",
    "left_source_record_id",
    "right_source",
    "right_record_ordinal",
    "right_source_record_id",
    "blocking_rules",
    "positive_evidence",
    "conflicts",
    "fs_log2_likelihood_ratio",
    "mct_score",
    "decision",
]


class FellegiSunterError(ValueError):
    """Raised when challenger training or application violates its frozen contract."""


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


def _events(row: Mapping[str, str]) -> tuple[str, ...]:
    evidence = (
        f"evidence:{feature}"
        for feature in filter(None, row.get("positive_evidence", "").split(";"))
    )
    conflicts = (
        f"conflict:{conflict}"
        for conflict in filter(None, row.get("conflicts", "").split(";"))
    )
    return tuple(sorted((*evidence, *conflicts)))


def _smoothed_probability(count: int, total: int, alpha: float) -> float:
    return (count + alpha) / (total + 2.0 * alpha)


def _decision(score: float) -> str:
    if score >= AUTO_MERGE_MINIMUM:
        return "auto_merge"
    if score >= HUMAN_REVIEW_MINIMUM:
        return "human_review"
    return "leave_separate"


def _posterior_from_log2_odds(log2_odds: float) -> float:
    if log2_odds >= 0:
        return 1.0 / (1.0 + math.pow(2.0, -log2_odds))
    odds = math.pow(2.0, log2_odds)
    return odds / (1.0 + odds)


def score_events(events: Iterable[str], model: Mapping[str, Any]) -> tuple[float, float, tuple[str, ...]]:
    """Return log2 likelihood ratio, posterior MCT score and unseen events."""

    prior = float(model["development_match_prior"])
    log2_odds = math.log2(prior / (1.0 - prior))
    likelihood_ratio = 0.0
    unseen: list[str] = []
    weights = model["events"]
    for event in sorted(set(events)):
        if event not in weights:
            unseen.append(event)
            continue
        weight = float(weights[event]["present_log2_likelihood_ratio"])
        likelihood_ratio += weight
        log2_odds += weight
    score = round(_posterior_from_log2_odds(log2_odds), 6)
    return round(likelihood_ratio, 6), score, tuple(unseen)


def _write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def estimate_fs_model(
    labelled_development_path: Path,
    output_dir: Path,
    *,
    alpha: float = DEFAULT_ALPHA,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Estimate present-event likelihood ratios from development labels only."""

    labelled_development_path = Path(labelled_development_path)
    output_dir = Path(output_dir)
    if not labelled_development_path.exists():
        raise FellegiSunterError(f"Development labels not found: {labelled_development_path}")
    if not math.isclose(alpha, 0.5):
        raise FellegiSunterError("The frozen challenger design requires Jeffreys alpha = 0.5")

    label_totals: Counter[str] = Counter()
    event_counts: dict[str, Counter[str]] = {
        "match": Counter(),
        "non_match": Counter(),
    }
    rows = 0
    try:
        with gzip.open(labelled_development_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            if not REQUIRED_TRAINING_COLUMNS.issubset(fields):
                raise FellegiSunterError(
                    f"Development labels are missing columns: {sorted(REQUIRED_TRAINING_COLUMNS - fields)}"
                )
            if any("person_id" in field.lower() for field in fields):
                raise FellegiSunterError("Development labels must not expose hidden person identifiers")
            for row_number, row in enumerate(reader, start=1):
                if row["partition"] != "development":
                    raise FellegiSunterError(
                        f"Training row {row_number} belongs to {row['partition']!r}, not development"
                    )
                label = row["truth_label"]
                if label not in event_counts:
                    raise FellegiSunterError(f"Unknown truth label {label!r} at training row {row_number}")
                label_totals[label] += 1
                event_counts[label].update(_events(row))
                rows += 1
    except OSError as exc:
        raise FellegiSunterError(f"Unable to read development labels: {exc}") from exc
    if not label_totals["match"] or not label_totals["non_match"]:
        raise FellegiSunterError("Development labels must contain matches and non-matches")

    event_model: dict[str, dict[str, Any]] = {}
    weight_rows: list[dict[str, Any]] = []
    for event in sorted(set(event_counts["match"]) | set(event_counts["non_match"])):
        match_count = event_counts["match"][event]
        nonmatch_count = event_counts["non_match"][event]
        m_probability = _smoothed_probability(match_count, label_totals["match"], alpha)
        u_probability = _smoothed_probability(nonmatch_count, label_totals["non_match"], alpha)
        weight = math.log2(m_probability / u_probability)
        values = {
            "match_event_count": match_count,
            "nonmatch_event_count": nonmatch_count,
            "m_probability": round(m_probability, 12),
            "u_probability": round(u_probability, 12),
            "present_log2_likelihood_ratio": round(weight, 6),
        }
        event_model[event] = values
        weight_rows.append({"event": event, **values})

    prior = _smoothed_probability(label_totals["match"], rows, alpha)
    model: dict[str, Any] = {
        "phase": "fellegi_sunter_weight_estimation",
        "model_version": FS_VERSION,
        "method": "sparse_present_event_log2_likelihood_ratio",
        "smoothing": {"method": "Jeffreys", "alpha": alpha},
        "thresholds": {
            "auto_merge_minimum": AUTO_MERGE_MINIMUM,
            "human_review_minimum": HUMAN_REVIEW_MINIMUM,
        },
        "training_partition": "development",
        "training_rows": rows,
        "training_match_rows": label_totals["match"],
        "training_nonmatch_rows": label_totals["non_match"],
        "development_match_prior": round(prior, 12),
        "events": event_model,
        "input": {
            "path": _portable_path(labelled_development_path),
            "sha256": _sha256(labelled_development_path),
        },
        "feature_contract": {
            "included": ["positive_evidence", "conflicts"],
            "event_absence_treatment": "neutral",
            "heuristic_mct_score_used": False,
            "heuristic_decision_used": False,
            "blocking_rule_used": False,
            "hard_negative_type_used": False,
            "record_identity_used": False,
            "person_identity_used": False,
            "validation_or_test_labels_used": False,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "fs_model.json"
    weights_path = output_dir / "fs_event_weights.csv"
    model_path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    _write_csv(
        weights_path,
        weight_rows,
        [
            "event",
            "match_event_count",
            "nonmatch_event_count",
            "m_probability",
            "u_probability",
            "present_log2_likelihood_ratio",
        ],
    )
    if show_progress:
        print(
            f"[fs-training] Complete: {rows:,} development pairs; "
            f"{len(event_model):,} empirical event weights"
        )
    return model


def _open_scores(path: Path) -> tuple[Any, Any, csv.DictWriter]:
    binary = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=FS_SCORE_COLUMNS)
    writer.writeheader()
    return binary, text, writer


def apply_fs_model(
    pair_features_path: Path,
    model_path: Path,
    output_dir: Path,
    *,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Apply frozen empirical weights without reading labels."""

    pair_features_path = Path(pair_features_path)
    model_path = Path(model_path)
    output_dir = Path(output_dir)
    for path in (pair_features_path, model_path):
        if not path.exists():
            raise FellegiSunterError(f"Required challenger input not found: {path}")
    try:
        model = json.loads(model_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FellegiSunterError(f"Unable to load frozen FS model: {exc}") from exc
    if model.get("training_partition") != "development":
        raise FellegiSunterError("FS model was not trained exclusively on development")
    if model.get("feature_contract", {}).get("validation_or_test_labels_used") is not False:
        raise FellegiSunterError("FS model does not prove holdout-label isolation")
    thresholds = model.get("thresholds", {})
    if not math.isclose(float(thresholds.get("auto_merge_minimum", -1)), AUTO_MERGE_MINIMUM):
        raise FellegiSunterError("Auto-merge threshold must remain exactly 0.88")
    if not math.isclose(float(thresholds.get("human_review_minimum", -1)), HUMAN_REVIEW_MINIMUM):
        raise FellegiSunterError("Review threshold must remain exactly 0.62")

    output_dir.mkdir(parents=True, exist_ok=True)
    score_path = output_dir / "fs_scored_candidate_pairs.csv.gz"
    binary, text_handle, writer = _open_scores(score_path)
    decisions: Counter[str] = Counter()
    unseen_events: Counter[str] = Counter()
    score_sum = 0.0
    scored = 0
    try:
        with gzip.open(pair_features_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            if not REQUIRED_SCORING_COLUMNS.issubset(fields):
                raise FellegiSunterError(
                    f"Pair feature input is missing: {sorted(REQUIRED_SCORING_COLUMNS - fields)}"
                )
            for row in reader:
                likelihood_ratio, score, unseen = score_events(_events(row), model)
                decision = _decision(score)
                writer.writerow(
                    {
                        **{column: row[column] for column in FS_SCORE_COLUMNS if column in row},
                        "fs_log2_likelihood_ratio": f"{likelihood_ratio:.6f}",
                        "mct_score": f"{score:.6f}",
                        "decision": decision,
                    }
                )
                decisions[decision] += 1
                unseen_events.update(unseen)
                score_sum += score
                scored += 1
    except OSError as exc:
        raise FellegiSunterError(f"Unable to read pair features: {exc}") from exc
    finally:
        text_handle.close()
        binary.close()

    manifest: dict[str, Any] = {
        "phase": "fellegi_sunter_mct_scoring",
        "scorer_version": FS_VERSION,
        "candidate_pairs_scored": scored,
        "thresholds": thresholds,
        "decision_counts": {name: decisions[name] for name in ("auto_merge", "human_review", "leave_separate")},
        "mean_mct_score": round(score_sum / scored, 6) if scored else 0.0,
        "unseen_event_counts": dict(sorted(unseen_events.items())),
        "inputs": {
            "pair_features": {"path": _portable_path(pair_features_path), "sha256": _sha256(pair_features_path)},
            "configuration": {"path": _portable_path(model_path), "sha256": _sha256(model_path)},
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
            "training_labels_encapsulated_in_frozen_model": True,
            "heuristic_mct_score_read_as_feature": False,
            "heuristic_decision_read_as_feature": False,
            "transitive_merging_performed": False,
            "clusters_formed": False,
        },
    }
    (output_dir / "fs_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    decision_rows = [
        {
            "decision": name,
            "mct_band": ">=0.88" if name == "auto_merge" else ">=0.62 and <0.88" if name == "human_review" else "<0.62",
            "pair_count": decisions[name],
            "percentage": round(100 * decisions[name] / scored, 6) if scored else 0.0,
        }
        for name in ("auto_merge", "human_review", "leave_separate")
    ]
    _write_csv(
        output_dir / "fs_decision_summary.csv",
        decision_rows,
        ["decision", "mct_band", "pair_count", "percentage"],
    )
    if show_progress:
        print(
            f"[fs-scoring] Complete: {scored:,} pairs; {decisions['auto_merge']:,} auto-merge, "
            f"{decisions['human_review']:,} review, {decisions['leave_separate']:,} separate"
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    train = subparsers.add_parser("train", help="Estimate weights from development labels")
    train.add_argument(
        "--development-labels",
        type=Path,
        default=Path("outputs/scoring/labelled_development_set.csv.gz"),
    )
    train.add_argument("--output-dir", type=Path, default=Path("outputs/fellegi_sunter"))
    score = subparsers.add_parser("score", help="Apply a frozen FS model to pair evidence")
    score.add_argument(
        "--pair-features",
        type=Path,
        default=Path("outputs/scoring/scored_candidate_pairs.csv.gz"),
    )
    score.add_argument("--model", type=Path, default=Path("outputs/fellegi_sunter/fs_model.json"))
    score.add_argument("--output-dir", type=Path, default=Path("outputs/fellegi_sunter"))
    args = parser.parse_args()
    try:
        if args.command == "train":
            estimate_fs_model(args.development_labels, args.output_dir)
        else:
            apply_fs_model(args.pair_features, args.model, args.output_dir)
    except FellegiSunterError as exc:
        print(f"[fellegi-sunter] ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
