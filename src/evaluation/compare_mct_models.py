"""Create a reproducible three-model MCT comparison using validation for selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


class ModelComparisonError(ValueError):
    """Raised when model evaluation artifacts cannot be compared safely."""


MODEL_LABELS = {
    "heuristic_mct": "Heuristic MCT",
    "fellegi_sunter_mct": "Fellegi-Sunter MCT",
    "logistic_regression_mct": "Logistic-regression MCT",
}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelComparisonError(f"Unable to load {path}: {exc}") from exc
    if value.get("scope") != "final":
        raise ModelComparisonError(f"Evaluation {path} must contain final partition metrics")
    partitions = value.get("pair_metrics_by_partition", {})
    if not {"development", "validation", "test"}.issubset(partitions):
        raise ModelComparisonError(f"Evaluation {path} is missing a model partition")
    return value


def select_from_validation(models: Mapping[str, Mapping[str, Any]]) -> str:
    """Select without consulting frozen-test metrics."""

    eligible = [
        name for name, model in models.items()
        if model["validation"]["auto_merge_false_positives"] == 0
    ]
    if not eligible:
        raise ModelComparisonError("No model passes the zero validation false-auto-merge gate")
    return max(
        eligible,
        key=lambda name: (
            models[name]["validation"]["auto_merge_recall_within_candidates"],
            models[name]["validation"]["assisted_recall_within_candidates"],
            -models[name]["validation"]["human_review_pairs"],
        ),
    )


def _compact(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: metrics[key]
        for key in (
            "candidate_pairs",
            "auto_merge_pairs",
            "auto_merge_true_positives",
            "auto_merge_false_positives",
            "auto_merge_precision",
            "auto_merge_recall_within_candidates",
            "human_review_pairs",
            "human_review_true_matches",
            "assisted_recall_within_candidates",
            "leave_separate_pairs",
        )
    }


def _report(result: Mapping[str, Any]) -> str:
    lines = [
        "# Three-model MCT comparison",
        "",
        "## Validation selection",
        "",
        "| Model | False auto-merges | Auto precision | Auto recall | Review pairs | Assisted recall |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, model in result["models"].items():
        metrics = model["validation"]
        lines.append(
            f"| {MODEL_LABELS[name]} | {metrics['auto_merge_false_positives']:,} | "
            f"{metrics['auto_merge_precision']:.4%} | {metrics['auto_merge_recall_within_candidates']:.4%} | "
            f"{metrics['human_review_pairs']:,} | {metrics['assisted_recall_within_candidates']:.4%} |"
        )
    lines.extend(
        [
            "",
            f"**Selected model:** {MODEL_LABELS[result['selected_model']]}",
            "",
            result["selection_reason"],
            "",
            "## Frozen-test characterization",
            "",
            "| Model | False auto-merges | Auto precision | Auto recall | Review pairs | Assisted recall |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, model in result["models"].items():
        metrics = model["frozen_test"]
        lines.append(
            f"| {MODEL_LABELS[name]} | {metrics['auto_merge_false_positives']:,} | "
            f"{metrics['auto_merge_precision']:.4%} | {metrics['auto_merge_recall_within_candidates']:.4%} | "
            f"{metrics['human_review_pairs']:,} | {metrics['assisted_recall_within_candidates']:.4%} |"
        )
    lines.extend(
        [
            "",
            "The frozen test was released only after the logistic validation decision was committed. It characterizes stability and does not participate in model selection.",
            "",
            "## Full-population operational effect",
            "",
            "| Model | Auto-merge edges | Review pairs | Leave separate | Hard-negative auto-merges |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, model in result["models"].items():
        decisions = model["full_population_decisions"]
        lines.append(
            f"| {MODEL_LABELS[name]} | {decisions['auto_merge']:,} | {decisions['human_review']:,} | "
            f"{decisions['leave_separate']:,} | {model['explicit_hard_negative_auto_merges']:,} |"
        )
    selected = result["models"][result["selected_model"]]
    lines.extend(
        [
            "",
            f"For the selected model, recoverable canonical-link auto recall is {selected['recoverable_canonical_auto_recall']:.4%} and auto-plus-review recall is {selected['recoverable_canonical_assisted_recall']:.4%}.",
            "",
        ]
    )
    return "\n".join(lines)


def compare_models(
    heuristic_path: Path,
    fs_path: Path,
    logistic_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    evaluations = {
        "heuristic_mct": _load(heuristic_path),
        "fellegi_sunter_mct": _load(fs_path),
        "logistic_regression_mct": _load(logistic_path),
    }
    models: dict[str, dict[str, Any]] = {}
    for name, evaluation in evaluations.items():
        full = evaluation["pair_metrics_by_partition"]
        decisions = {
            decision: sum(full[partition][f"{decision}_pairs"] for partition in full)
            if decision != "leave_separate"
            else sum(full[partition]["leave_separate_pairs"] for partition in full)
            for decision in ("auto_merge", "human_review", "leave_separate")
        }
        canonical = evaluation["canonical_link_metrics"]
        models[name] = {
            "validation": _compact(full["validation"]),
            "frozen_test": _compact(full["test"]),
            "full_population_decisions": decisions,
            "explicit_hard_negative_auto_merges": evaluation["hard_negative_metrics"]["overall"]["auto_merge"],
            "recoverable_canonical_auto_recall": canonical["recoverable_auto_merge_recall"],
            "recoverable_canonical_assisted_recall": canonical["recoverable_assisted_recall"],
        }
    selected = select_from_validation(models)
    result: dict[str, Any] = {
        "phase": "three_model_mct_comparison",
        "selection_partition": "validation",
        "selection_policy": [
            "require_zero_false_auto_merges",
            "maximize_auto_merge_recall",
            "maximize_assisted_recall",
            "minimize_review_pairs",
        ],
        "frozen_test_used_for_selection": False,
        "selected_model": selected,
        "selection_reason": (
            "Fellegi-Sunter is ineligible because it produced one validation false auto-merge. "
            "Logistic regression matches the heuristic's zero false auto-merges while materially "
            "improving auto and assisted recall, so it wins the predeclared validation ordering."
        ),
        "models": models,
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logistic_comparison.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "logistic_comparison.md").write_text(_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heuristic", type=Path, default=Path("outputs/scoring/mct_evaluation.json"))
    parser.add_argument("--fellegi-sunter", type=Path, default=Path("outputs/fellegi_sunter/mct_evaluation.json"))
    parser.add_argument("--logistic", type=Path, default=Path("outputs/logistic/mct_evaluation.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/logistic"))
    args = parser.parse_args()
    try:
        result = compare_models(args.heuristic, args.fellegi_sunter, args.logistic, args.output_dir)
    except ModelComparisonError as exc:
        print(f"[model-comparison] ERROR: {exc}")
        return 1
    print(f"[model-comparison] Selected on validation: {result['selected_model']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
