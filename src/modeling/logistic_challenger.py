"""Train, validate and apply an interpretable logistic-regression MCT challenger.

The statistical model is ordinary binary logistic regression with L2 regularization.
NumPy is used directly because the workstation's Application Control policy blocks a
compiled SciPy component required by scikit-learn.
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
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


MODEL_VERSION = 1
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "logistic_challenger.yaml"
REQUIRED_LABEL_COLUMNS = {"positive_evidence", "conflicts", "truth_label", "partition"}
PAIR_ID_COLUMNS = [
    "left_source",
    "left_record_ordinal",
    "left_source_record_id",
    "right_source",
    "right_record_ordinal",
    "right_source_record_id",
    "blocking_rules",
    "positive_evidence",
    "conflicts",
]
SCORE_COLUMNS = [*PAIR_ID_COLUMNS, "mct_score", "decision"]


class LogisticChallengerError(ValueError):
    """Raised when an ML challenger boundary or artifact contract is violated."""


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


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LogisticChallengerError(f"Unable to load logistic configuration: {exc}") from exc
    events = config.get("base_events")
    if not isinstance(events, list) or not events or len(events) != len(set(events)):
        raise LogisticChallengerError("base_events must be a nonempty unique list")
    if events != sorted(events):
        raise LogisticChallengerError("base_events must be sorted for deterministic features")
    if config.get("interaction_policy") != "all_unordered_pairs_of_distinct_base_events":
        raise LogisticChallengerError("Only the frozen all-pairwise interaction policy is supported")
    thresholds = config.get("thresholds", {})
    if thresholds != {"auto_merge_minimum": 0.88, "human_review_minimum": 0.62}:
        raise LogisticChallengerError("The assessment MCT thresholds must remain exactly 0.88 and 0.62")
    strengths = config.get("regularization", {}).get("candidate_strengths")
    if strengths != [0.0001, 0.001, 0.01, 0.1]:
        raise LogisticChallengerError("Regularization candidates differ from the frozen design")
    return config


def feature_names(config: Mapping[str, Any]) -> list[str]:
    base = list(config["base_events"])
    return [*base, *(f"{left} & {right}" for left, right in combinations(base, 2))]


def _row_events(row: Mapping[str, str]) -> set[str]:
    evidence = {
        f"evidence:{value}"
        for value in row.get("positive_evidence", "").split(";")
        if value
    }
    conflicts = {
        f"conflict:{value}"
        for value in row.get("conflicts", "").split(";")
        if value
    }
    return evidence | conflicts


def encode_rows(rows: Sequence[Mapping[str, str]], config: Mapping[str, Any]) -> np.ndarray:
    """Encode base binary events and every unordered pairwise interaction."""

    base_names = list(config["base_events"])
    lookup = {name: index for index, name in enumerate(base_names)}
    base = np.zeros((len(rows), len(base_names)), dtype=np.float64)
    for row_index, row in enumerate(rows):
        events = _row_events(row)
        unknown = events - set(lookup)
        if unknown:
            raise LogisticChallengerError(f"Unknown scoring events: {sorted(unknown)}")
        for event in events:
            base[row_index, lookup[event]] = 1.0
    columns: list[np.ndarray] = [base]
    columns.extend(
        (base[:, left] * base[:, right]).reshape(-1, 1)
        for left, right in combinations(range(len(base_names)), 2)
    )
    return np.concatenate(columns, axis=1)


def _load_labelled_rows(path: Path, required_partition: str) -> tuple[list[dict[str, str]], np.ndarray]:
    path = Path(path)
    if required_partition not in {"development", "validation", "test"}:
        raise LogisticChallengerError(f"Unknown required partition {required_partition!r}")
    if not path.exists():
        raise LogisticChallengerError(f"Labelled input not found: {path}")
    rows: list[dict[str, str]] = []
    labels: list[float] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            if not REQUIRED_LABEL_COLUMNS.issubset(fields):
                raise LogisticChallengerError(
                    f"Labelled input is missing columns: {sorted(REQUIRED_LABEL_COLUMNS - fields)}"
                )
            if any("person_id" in field.lower() for field in fields):
                raise LogisticChallengerError("Labelled model inputs must not expose person identifiers")
            for row_number, row in enumerate(reader, start=1):
                if row["partition"] != required_partition:
                    raise LogisticChallengerError(
                        f"Row {row_number} belongs to {row['partition']!r}, not {required_partition!r}"
                    )
                label = row["truth_label"]
                if label not in {"match", "non_match"}:
                    raise LogisticChallengerError(f"Unknown label {label!r} at row {row_number}")
                rows.append(row)
                labels.append(1.0 if label == "match" else 0.0)
    except OSError as exc:
        raise LogisticChallengerError(f"Unable to read labelled input: {exc}") from exc
    if not rows or len(set(labels)) != 2:
        raise LogisticChallengerError("Labelled input must contain both matches and non-matches")
    return rows, np.asarray(labels, dtype=np.float64)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -35.0, 35.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _probabilities(matrix: np.ndarray, intercept: float, coefficients: np.ndarray) -> np.ndarray:
    return _sigmoid(matrix @ coefficients + intercept)


def _decision(score: float) -> str:
    if score >= 0.88:
        return "auto_merge"
    if score >= 0.62:
        return "human_review"
    return "leave_separate"


def _binary_metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    auto = probabilities >= 0.88
    review = (probabilities >= 0.62) & ~auto
    positive = labels == 1.0
    negative = ~positive
    true_matches = int(np.sum(positive))
    auto_true = int(np.sum(auto & positive))
    auto_false = int(np.sum(auto & negative))
    review_true = int(np.sum(review & positive))
    clipped = np.clip(probabilities, 1e-15, 1.0 - 1e-15)
    bins: list[dict[str, Any]] = []
    expected_calibration_error = 0.0
    for index in range(10):
        lower, upper = index / 10.0, (index + 1) / 10.0
        mask = (probabilities >= lower) & (
            probabilities <= upper if index == 9 else probabilities < upper
        )
        count = int(np.sum(mask))
        if count:
            mean_score = float(np.mean(probabilities[mask]))
            observed = float(np.mean(labels[mask]))
            expected_calibration_error += count / len(labels) * abs(mean_score - observed)
        else:
            mean_score = None
            observed = None
        bins.append(
            {
                "lower_inclusive": lower,
                "upper_inclusive": index == 9,
                "upper": upper,
                "pairs": count,
                "mean_score": mean_score,
                "observed_match_rate": observed,
            }
        )
    return {
        "candidate_pairs": len(labels),
        "true_match_pairs": true_matches,
        "true_non_match_pairs": int(np.sum(negative)),
        "auto_merge_pairs": int(np.sum(auto)),
        "auto_merge_true_positives": auto_true,
        "auto_merge_false_positives": auto_false,
        "auto_merge_precision": auto_true / (auto_true + auto_false) if auto_true + auto_false else None,
        "auto_merge_recall_within_candidates": auto_true / true_matches,
        "human_review_pairs": int(np.sum(review)),
        "human_review_true_matches": review_true,
        "assisted_recall_within_candidates": (auto_true + review_true) / true_matches,
        "leave_separate_pairs": int(np.sum(~auto & ~review)),
        "log_loss": float(-np.mean(labels * np.log(clipped) + (1.0 - labels) * np.log(1.0 - clipped))),
        "brier_score": float(np.mean((probabilities - labels) ** 2)),
        "expected_calibration_error_10_bins": expected_calibration_error,
        "calibration_bins": bins,
    }


def _fit_one(
    matrix: np.ndarray,
    labels: np.ndarray,
    l2_strength: float,
    optimizer: Mapping[str, Any],
) -> tuple[float, np.ndarray]:
    rows, columns = matrix.shape
    prior = (float(np.sum(labels)) + 0.5) / (rows + 1.0)
    intercept = math.log(prior / (1.0 - prior))
    coefficients = np.zeros(columns, dtype=np.float64)
    first_moment = np.zeros(columns + 1, dtype=np.float64)
    second_moment = np.zeros(columns + 1, dtype=np.float64)
    beta1 = float(optimizer["beta1"])
    beta2 = float(optimizer["beta2"])
    epsilon = float(optimizer["epsilon"])
    learning_rate = float(optimizer["learning_rate"])
    batch_size = int(optimizer["batch_size"])
    step = 0
    for _epoch in range(int(optimizer["epochs"])):
        for start in range(0, rows, batch_size):
            stop = min(start + batch_size, rows)
            batch = matrix[start:stop]
            batch_labels = labels[start:stop]
            errors = _probabilities(batch, intercept, coefficients) - batch_labels
            gradient = np.empty(columns + 1, dtype=np.float64)
            gradient[0] = float(np.mean(errors))
            gradient[1:] = batch.T @ errors / len(batch) + l2_strength * coefficients
            step += 1
            first_moment = beta1 * first_moment + (1.0 - beta1) * gradient
            second_moment = beta2 * second_moment + (1.0 - beta2) * (gradient * gradient)
            corrected_first = first_moment / (1.0 - beta1**step)
            corrected_second = second_moment / (1.0 - beta2**step)
            update = learning_rate * corrected_first / (np.sqrt(corrected_second) + epsilon)
            intercept -= float(update[0])
            coefficients -= update[1:]
    return intercept, coefficients


def train_candidates(
    development_path: Path,
    output_dir: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Fit every frozen L2 candidate using development labels only."""

    config = load_config(config_path)
    rows, labels = _load_labelled_rows(development_path, "development")
    matrix = encode_rows(rows, config)
    names = feature_names(config)
    candidates: list[dict[str, Any]] = []
    coefficient_rows: list[dict[str, Any]] = []
    for strength in config["regularization"]["candidate_strengths"]:
        if show_progress:
            print(f"[logistic-training] Fitting L2={strength:g} on {len(rows):,} development pairs")
        intercept, coefficients = _fit_one(matrix, labels, float(strength), config["optimizer"])
        metrics = _binary_metrics(labels, _probabilities(matrix, intercept, coefficients))
        candidate_id = f"logistic_l2_{strength:g}"
        candidate = {
            "candidate_id": candidate_id,
            "l2_strength": strength,
            "intercept": intercept,
            "coefficients": {name: float(value) for name, value in zip(names, coefficients)},
            "development_metrics": metrics,
        }
        candidates.append(candidate)
        coefficient_rows.append({"candidate_id": candidate_id, "feature": "(intercept)", "coefficient": intercept})
        coefficient_rows.extend(
            {"candidate_id": candidate_id, "feature": name, "coefficient": float(value)}
            for name, value in zip(names, coefficients)
        )
    bundle: dict[str, Any] = {
        "phase": "logistic_challenger_training",
        "model_version": MODEL_VERSION,
        "method": "binary_logistic_regression_with_l2",
        "implementation": "numpy_deterministic_minibatch_adam",
        "training_partition": "development",
        "training_rows": len(rows),
        "training_match_rows": int(np.sum(labels)),
        "training_nonmatch_rows": int(len(labels) - np.sum(labels)),
        "feature_count": len(names),
        "base_feature_count": len(config["base_events"]),
        "interaction_feature_count": len(names) - len(config["base_events"]),
        "feature_names": names,
        "candidates": candidates,
        "input": {"path": _portable_path(development_path), "sha256": _sha256(development_path)},
        "configuration": {"path": _portable_path(config_path), "sha256": _sha256(config_path)},
        "feature_contract": {
            "included": ["positive_evidence", "conflicts", "all_pairwise_event_interactions"],
            "heuristic_mct_score_used": False,
            "heuristic_decision_used": False,
            "blocking_rule_used": False,
            "hard_negative_type_used": False,
            "record_identity_used": False,
            "person_identity_used": False,
            "validation_or_test_labels_used": False,
        },
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logistic_candidates.json").write_text(
        json.dumps(bundle, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "logistic_coefficients.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate_id", "feature", "coefficient"])
        writer.writeheader()
        writer.writerows(coefficient_rows)
    return bundle


def _model_probabilities(matrix: np.ndarray, candidate: Mapping[str, Any], names: Sequence[str]) -> np.ndarray:
    coefficients = np.asarray([candidate["coefficients"][name] for name in names], dtype=np.float64)
    return _probabilities(matrix, float(candidate["intercept"]), coefficients)


def _heuristic_metrics(rows: Sequence[Mapping[str, str]], labels: np.ndarray) -> dict[str, Any] | None:
    if not rows or "mct_score" not in rows[0]:
        return None
    return _binary_metrics(labels, np.asarray([float(row["mct_score"]) for row in rows]))


def _validation_report(result: Mapping[str, Any]) -> str:
    selected = result.get("selected_candidate")
    lines = [
        "# Logistic challenger validation decision",
        "",
        f"**Frozen-test status:** {result['frozen_test_status']}",
        "",
        f"**Decision:** {result['decision']}",
        "",
        "| Candidate | L2 | False auto-merges | Auto precision | Auto recall | Review pairs | Assisted recall | Brier |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    baseline = result.get("heuristic_validation_metrics")
    if baseline:
        lines.append(
            f"| Heuristic baseline | n/a | {baseline['auto_merge_false_positives']:,} | "
            f"{baseline['auto_merge_precision']:.4%} | {baseline['auto_merge_recall_within_candidates']:.4%} | "
            f"{baseline['human_review_pairs']:,} | {baseline['assisted_recall_within_candidates']:.4%} | "
            f"{baseline['brier_score']:.6f} |"
        )
    for item in result["candidate_validation_metrics"]:
        metrics = item["metrics"]
        lines.append(
            f"| {item['candidate_id']} | {item['l2_strength']:g} | "
            f"{metrics['auto_merge_false_positives']:,} | {metrics['auto_merge_precision']:.4%} | "
            f"{metrics['auto_merge_recall_within_candidates']:.4%} | {metrics['human_review_pairs']:,} | "
            f"{metrics['assisted_recall_within_candidates']:.4%} | {metrics['brier_score']:.6f} |"
        )
    lines.extend(["", "## Gate result", ""])
    if selected:
        lines.append(
            f"`{selected['candidate_id']}` passes the zero-false-auto-merge gate and ranks first "
            "under the predeclared validation ordering. Its coefficients are frozen before the test is opened."
        )
    else:
        lines.append("No candidate passes the zero-false-auto-merge validation gate; the challenger is rejected.")
    lines.extend(
        [
            "",
            "The mandatory 0.88/0.62 thresholds were not tuned. Validation was not used to fit a post-hoc calibration transform.",
            "",
        ]
    )
    return "\n".join(lines)


def select_on_validation(
    validation_path: Path,
    candidates_path: Path,
    output_dir: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Apply the predeclared validation gate without opening frozen-test labels."""

    config = load_config(config_path)
    try:
        bundle = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LogisticChallengerError(f"Unable to load trained candidates: {exc}") from exc
    if bundle.get("training_partition") != "development":
        raise LogisticChallengerError("Candidate bundle was not trained exclusively on development")
    if bundle.get("configuration", {}).get("sha256") != _sha256(config_path):
        raise LogisticChallengerError("Candidate bundle does not match the frozen configuration")
    names = feature_names(config)
    if bundle.get("feature_names") != names:
        raise LogisticChallengerError("Candidate feature order differs from the frozen design")
    rows, labels = _load_labelled_rows(validation_path, "validation")
    matrix = encode_rows(rows, config)
    evaluated: list[dict[str, Any]] = []
    for candidate in bundle["candidates"]:
        metrics = _binary_metrics(labels, _model_probabilities(matrix, candidate, names))
        evaluated.append(
            {
                "candidate_id": candidate["candidate_id"],
                "l2_strength": candidate["l2_strength"],
                "passes_zero_false_auto_merge_gate": metrics["auto_merge_false_positives"] == 0,
                "metrics": metrics,
            }
        )
    eligible = [item for item in evaluated if item["passes_zero_false_auto_merge_gate"]]
    selected_summary = None
    selected_model = None
    if eligible:
        selected_summary = max(
            eligible,
            key=lambda item: (
                item["metrics"]["auto_merge_recall_within_candidates"],
                item["metrics"]["assisted_recall_within_candidates"],
                -item["metrics"]["human_review_pairs"],
                item["l2_strength"],
            ),
        )
        selected_model = next(
            candidate for candidate in bundle["candidates"]
            if candidate["candidate_id"] == selected_summary["candidate_id"]
        )
    result: dict[str, Any] = {
        "phase": "logistic_challenger_validation_selection",
        "selection_partition": "validation",
        "frozen_test_status": "not opened by logistic challenger",
        "thresholds_tuned": False,
        "posthoc_calibration_fitted": False,
        "decision": "accept logistic candidate for frozen-test characterization" if selected_model else "reject logistic challenger",
        "heuristic_validation_metrics": _heuristic_metrics(rows, labels),
        "candidate_validation_metrics": evaluated,
        "selected_candidate": selected_summary,
        "inputs": {
            "validation": {"path": _portable_path(validation_path), "sha256": _sha256(validation_path)},
            "candidates": {"path": _portable_path(candidates_path), "sha256": _sha256(candidates_path)},
            "configuration": {"path": _portable_path(config_path), "sha256": _sha256(config_path)},
        },
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logistic_validation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "logistic_validation.md").write_text(_validation_report(result), encoding="utf-8")
    if selected_model:
        frozen_model = {
            "phase": "selected_logistic_challenger_model",
            "model_version": MODEL_VERSION,
            "candidate_id": selected_model["candidate_id"],
            "l2_strength": selected_model["l2_strength"],
            "intercept": selected_model["intercept"],
            "coefficients": selected_model["coefficients"],
            "feature_names": names,
            "thresholds": config["thresholds"],
            "training_input_sha256": bundle["input"]["sha256"],
            "configuration_sha256": _sha256(config_path),
            "validation_selection_sha256": _sha256(output_dir / "logistic_validation.json"),
            "frozen_test_labels_used": False,
            "feature_contract": bundle["feature_contract"],
        }
        (output_dir / "logistic_model.json").write_text(
            json.dumps(frozen_model, indent=2) + "\n", encoding="utf-8"
        )
    if show_progress:
        print(
            f"[logistic-validation] {result['decision']}; "
            f"selected={selected_summary['candidate_id'] if selected_summary else 'none'}"
        )
    return result


def _open_gzip_csv(path: Path) -> tuple[Any, Any, csv.DictWriter]:
    binary = Path(path).open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=SCORE_COLUMNS)
    writer.writeheader()
    return binary, text, writer


def apply_model(
    pair_features_path: Path,
    model_path: Path,
    output_dir: Path,
    *,
    config_path: Path = DEFAULT_CONFIG,
    show_progress: bool = True,
) -> dict[str, Any]:
    """Score truth-free candidate features with the frozen selected model."""

    config = load_config(config_path)
    try:
        model = json.loads(Path(model_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LogisticChallengerError(f"Unable to load selected model: {exc}") from exc
    if model.get("frozen_test_labels_used") is not False:
        raise LogisticChallengerError("Selected model does not prove frozen-test isolation")
    if model.get("configuration_sha256") != _sha256(config_path):
        raise LogisticChallengerError("Selected model does not match the frozen configuration")
    names = feature_names(config)
    if model.get("feature_names") != names:
        raise LogisticChallengerError("Selected model feature order differs from configuration")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    score_path = output_dir / "logistic_scored_candidate_pairs.csv.gz"
    binary, text_handle, writer = _open_gzip_csv(score_path)
    decisions: Counter[str] = Counter()
    scored = 0
    batch: list[dict[str, str]] = []

    def write_batch() -> None:
        nonlocal scored
        if not batch:
            return
        matrix = encode_rows(batch, config)
        probabilities = _model_probabilities(matrix, model, names)
        for row, probability in zip(batch, probabilities):
            rounded = round(float(probability), 6)
            decision = _decision(rounded)
            writer.writerow({**{column: row[column] for column in PAIR_ID_COLUMNS}, "mct_score": f"{rounded:.6f}", "decision": decision})
            decisions[decision] += 1
            scored += 1
        batch.clear()

    try:
        with gzip.open(pair_features_path, "rt", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            missing = set(PAIR_ID_COLUMNS) - fields
            if missing:
                raise LogisticChallengerError(f"Pair features are missing columns: {sorted(missing)}")
            if "truth_label" in fields or any("person_id" in field.lower() for field in fields):
                raise LogisticChallengerError("Production scoring input must not contain evaluation labels or person IDs")
            for row in reader:
                batch.append(row)
                if len(batch) == 8192:
                    write_batch()
            write_batch()
    finally:
        text_handle.close()
        binary.close()
    manifest: dict[str, Any] = {
        "phase": "logistic_challenger_scoring",
        "model_version": MODEL_VERSION,
        "candidate_pairs_scored": scored,
        "decision_counts": {name: decisions[name] for name in ("auto_merge", "human_review", "leave_separate")},
        "thresholds": config["thresholds"],
        "inputs": {
            "pair_features": {"path": _portable_path(pair_features_path), "sha256": _sha256(pair_features_path)},
            "model": {"path": _portable_path(model_path), "sha256": _sha256(model_path)},
            "configuration": {"path": _portable_path(config_path), "sha256": _sha256(config_path)},
        },
        "scored_output": {
            "path": _portable_path(score_path),
            "compression": "gzip",
            "rows": scored,
            "sha256": _sha256(score_path),
        },
        "phase_boundaries": {
            "evaluation_labels_read": False,
            "hidden_person_identifiers_read": False,
            "heuristic_scores_used_as_features": False,
            "clusters_formed": False,
        },
    }
    (output_dir / "logistic_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "logistic_decision_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        summary = csv.DictWriter(handle, fieldnames=["decision", "pair_count", "percentage"])
        summary.writeheader()
        for decision in ("auto_merge", "human_review", "leave_separate"):
            summary.writerow(
                {
                    "decision": decision,
                    "pair_count": decisions[decision],
                    "percentage": 100.0 * decisions[decision] / scored if scored else 0.0,
                }
            )
    if show_progress:
        print(f"[logistic-scoring] Complete: {scored:,} candidate pairs scored")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    train = subparsers.add_parser("train", help="Fit frozen L2 candidates on development only")
    train.add_argument("--development-labels", type=Path, default=Path("outputs/scoring/labelled_development_set.csv.gz"))
    train.add_argument("--output-dir", type=Path, default=Path("outputs/logistic"))
    train.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    validate = subparsers.add_parser("validate", help="Select a frozen candidate on validation")
    validate.add_argument("--validation-labels", type=Path, default=Path("outputs/scoring/labelled_validation_set.csv.gz"))
    validate.add_argument("--candidates", type=Path, default=Path("outputs/logistic/logistic_candidates.json"))
    validate.add_argument("--output-dir", type=Path, default=Path("outputs/logistic"))
    validate.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    score = subparsers.add_parser("score", help="Apply the selected model to truth-free pair features")
    score.add_argument("--pair-features", type=Path, default=Path("outputs/scoring/scored_candidate_pairs.csv.gz"))
    score.add_argument("--model", type=Path, default=Path("outputs/logistic/logistic_model.json"))
    score.add_argument("--output-dir", type=Path, default=Path("outputs/logistic"))
    score.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    try:
        if args.command == "train":
            train_candidates(args.development_labels, args.output_dir, config_path=args.config)
        elif args.command == "validate":
            select_on_validation(args.validation_labels, args.candidates, args.output_dir, config_path=args.config)
        else:
            apply_model(args.pair_features, args.model, args.output_dir, config_path=args.config)
    except LogisticChallengerError as exc:
        print(f"[logistic-challenger] ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
