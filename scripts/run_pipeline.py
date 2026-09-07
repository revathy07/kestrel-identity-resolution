"""Run the Kestrel identity-resolution workflow in one isolated, fail-fast command."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_WRITE_ATTEMPTS = 8
REQUIRED_SOURCE_FILES = (
    "app_users.csv",
    "store_customers.csv",
    "ticketing.jl",
    "subscriptions.xlsx",
    "social_logins.json",
    "generation_report.json",
    "person_map.csv",
    "hard_negatives.json",
    "hidden/canonical_duplicate_links.jsonl",
)


class PipelineError(RuntimeError):
    """Raised when a run cannot safely start or a stage fails its contract."""


@dataclass(frozen=True)
class PipelineStep:
    """One subprocess and the artifacts that prove it completed."""

    name: str
    description: str
    command: tuple[str, ...]
    expected_outputs: tuple[Path, ...] = ()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_run_dir(mode: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return PROJECT_ROOT / "runs" / f"{stamp}-{mode}"


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path, run_dir: Path) -> dict[str, Any]:
    try:
        portable = path.relative_to(run_dir).as_posix()
    except ValueError:
        portable = str(path)
    return {"path": portable, "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def _module(name: str, *arguments: object) -> tuple[str, ...]:
    return (sys.executable, "-m", name, *(str(argument) for argument in arguments))


def _script(path: str, *arguments: object) -> tuple[str, ...]:
    return (sys.executable, str(PROJECT_ROOT / path), *(str(argument) for argument in arguments))


def build_steps(
    data_dir: Path,
    output_dir: Path,
    *,
    generate: bool,
    scale: float,
    seed: int,
    include_compliance_audit: bool,
    complete_release: bool,
    include_tests: bool,
) -> list[PipelineStep]:
    """Build the frozen dependency order without executing it."""

    validation = output_dir / "dataset-validation"
    profiling = output_dir / "profiling"
    normalization = output_dir / "normalization"
    blocking = output_dir / "blocking"
    scoring = output_dir / "scoring"
    fs = output_dir / "fellegi_sunter"
    logistic = output_dir / "logistic"
    heuristic_clusters = output_dir / "heuristic-clustering"
    clusters = output_dir / "clustering"
    evaluation = output_dir / "evaluation"
    business = output_dir / "business"
    normalized = normalization / "normalized_identifiers.csv.gz"
    candidates = blocking / "candidate_pairs.csv.gz"
    rule2 = blocking / "normalized_rule2_registry.json"
    heuristic_scores = scoring / "scored_candidate_pairs.csv.gz"
    fs_scores = fs / "fs_scored_candidate_pairs.csv.gz"
    logistic_scores = logistic / "logistic_scored_candidate_pairs.csv.gz"
    truth = data_dir / "person_map.csv"
    canonical = data_dir / "hidden" / "canonical_duplicate_links.jsonl"
    hard_negatives = data_dir / "hard_negatives.json"

    steps: list[PipelineStep] = []
    if generate:
        steps.append(
            PipelineStep(
                "generate_dataset",
                "Generate deterministic synthetic source systems and hidden truth.",
                _script(
                    "scripts/generate_synthetic_dataset.py",
                    "--scale",
                    scale,
                    "--seed",
                    seed,
                    "--output-dir",
                    data_dir,
                ),
                tuple(data_dir / name for name in REQUIRED_SOURCE_FILES),
            )
        )
    steps.append(
        PipelineStep(
            "independent_dataset_verification",
            "Run the scale-aware independent dataset-constraint verifier.",
            _script("scripts/verify_synthetic_dataset.py", "--data-dir", data_dir),
        )
    )
    if include_compliance_audit:
        steps.append(
            PipelineStep(
                "dataset_compliance_audit",
                "Write the strict full-scale requirement-level dataset audit.",
                _module(
                    "src.validate_generated_data",
                    "--data-dir",
                    data_dir,
                    "--output-dir",
                    validation,
                ),
                (validation / "dataset_audit_results.json", validation / "dataset_audit_report.md"),
            )
        )
    steps.extend(
        [
            PipelineStep(
                "profile_identifiers",
                "Profile all sources and discover raw Rule 2 values.",
                _module(
                    "src.profiling.profile_identifiers",
                    "--data-dir",
                    data_dir,
                    "--output-dir",
                    profiling,
                ),
                (profiling / "data_quality_summary.json", profiling / "rule2_registry.json"),
            ),
            PipelineStep(
                "normalize_identifiers",
                "Create derived comparable identifiers without changing raw data.",
                _module(
                    "src.normalization.normalize_identifiers",
                    "--data-dir",
                    data_dir,
                    "--output-dir",
                    normalization,
                ),
                (normalized, normalization / "normalization_manifest.json"),
            ),
            PipelineStep(
                "generate_candidates",
                "Apply normalized Rule 2 and construct candidate pairs.",
                _module(
                    "src.blocking.generate_candidates",
                    "--normalized-path",
                    normalized,
                    "--output-dir",
                    blocking,
                ),
                (candidates, rule2, blocking / "candidate_manifest.json"),
            ),
            PipelineStep(
                "evaluate_blocking",
                "Measure candidate recall after truth-free candidate generation.",
                _module(
                    "src.evaluation.evaluate_blocking",
                    "--candidate-path",
                    candidates,
                    "--canonical-links",
                    canonical,
                    "--hard-negatives",
                    hard_negatives,
                    "--output-dir",
                    blocking,
                ),
                (blocking / "blocking_evaluation.json",),
            ),
            PipelineStep(
                "score_heuristic_mct",
                "Create explainable pair features and heuristic MCT decisions without labels.",
                _module(
                    "src.scoring.score_candidates",
                    "--normalized-path",
                    normalized,
                    "--candidate-path",
                    candidates,
                    "--rule2-registry",
                    rule2,
                    "--output-dir",
                    scoring,
                ),
                (heuristic_scores, scoring / "mct_manifest.json"),
            ),
            PipelineStep(
                "release_development_labels",
                "Open truth only in the evaluator and release the development partition.",
                _module(
                    "src.evaluation.evaluate_scoring",
                    "--scored-path",
                    heuristic_scores,
                    "--scoring-manifest",
                    scoring / "mct_manifest.json",
                    "--truth-map",
                    truth,
                    "--canonical-links",
                    canonical,
                    "--hard-negatives",
                    hard_negatives,
                    "--output-dir",
                    scoring,
                    "--scope",
                    "development",
                ),
                (scoring / "labelled_development_set.csv.gz", scoring / "mct_development_evaluation.json"),
            ),
            PipelineStep(
                "train_fellegi_sunter",
                "Estimate empirical likelihood-ratio weights from development labels only.",
                _module(
                    "src.modeling.fellegi_sunter",
                    "train",
                    "--development-labels",
                    scoring / "labelled_development_set.csv.gz",
                    "--output-dir",
                    fs,
                ),
                (fs / "fs_model.json",),
            ),
            PipelineStep(
                "score_fellegi_sunter",
                "Apply the frozen Fellegi-Sunter model to truth-free pair features.",
                _module(
                    "src.modeling.fellegi_sunter",
                    "score",
                    "--pair-features",
                    heuristic_scores,
                    "--model",
                    fs / "fs_model.json",
                    "--output-dir",
                    fs,
                ),
                (fs_scores, fs / "fs_manifest.json"),
            ),
            PipelineStep(
                "release_validation_labels",
                "Release the person-disjoint validation partition for model selection.",
                _module(
                    "src.evaluation.evaluate_scoring",
                    "--scored-path",
                    heuristic_scores,
                    "--scoring-manifest",
                    scoring / "mct_manifest.json",
                    "--truth-map",
                    truth,
                    "--canonical-links",
                    canonical,
                    "--hard-negatives",
                    hard_negatives,
                    "--output-dir",
                    scoring,
                    "--scope",
                    "validation",
                ),
                (scoring / "labelled_validation_set.csv.gz", scoring / "mct_validation_evaluation.json"),
            ),
            PipelineStep(
                "evaluate_fellegi_sunter_validation",
                "Evaluate frozen Fellegi-Sunter decisions on development and validation only.",
                _module(
                    "src.evaluation.evaluate_scoring",
                    "--scored-path",
                    fs_scores,
                    "--scoring-manifest",
                    fs / "fs_manifest.json",
                    "--truth-map",
                    truth,
                    "--canonical-links",
                    canonical,
                    "--hard-negatives",
                    hard_negatives,
                    "--output-dir",
                    fs,
                    "--scope",
                    "validation",
                ),
                (fs / "mct_validation_evaluation.json",),
            ),
            PipelineStep(
                "train_logistic_candidates",
                "Fit predeclared logistic candidates on development labels only.",
                _module(
                    "src.modeling.logistic_challenger",
                    "train",
                    "--development-labels",
                    scoring / "labelled_development_set.csv.gz",
                    "--output-dir",
                    logistic,
                ),
                (logistic / "logistic_candidates.json",),
            ),
            PipelineStep(
                "select_logistic_on_validation",
                "Select regularization using validation without opening frozen test.",
                _module(
                    "src.modeling.logistic_challenger",
                    "validate",
                    "--validation-labels",
                    scoring / "labelled_validation_set.csv.gz",
                    "--candidates",
                    logistic / "logistic_candidates.json",
                    "--output-dir",
                    logistic,
                ),
                (logistic / "logistic_model.json", logistic / "logistic_validation.json"),
            ),
            PipelineStep(
                "score_logistic_mct",
                "Apply the selected logistic model to truth-free pair features.",
                _module(
                    "src.modeling.logistic_challenger",
                    "score",
                    "--pair-features",
                    heuristic_scores,
                    "--model",
                    logistic / "logistic_model.json",
                    "--output-dir",
                    logistic,
                ),
                (logistic_scores, logistic / "logistic_manifest.json"),
            ),
        ]
    )

    evaluation_specs = (
        ("heuristic", heuristic_scores, scoring / "mct_manifest.json", scoring),
        ("fellegi_sunter", fs_scores, fs / "fs_manifest.json", fs),
        ("logistic", logistic_scores, logistic / "logistic_manifest.json", logistic),
    )
    for label, scores, manifest, destination in evaluation_specs:
        steps.append(
            PipelineStep(
                f"evaluate_{label}_frozen_test",
                f"Release the frozen test for the {label.replace('_', ' ')} MCT.",
                _module(
                    "src.evaluation.evaluate_scoring",
                    "--scored-path",
                    scores,
                    "--scoring-manifest",
                    manifest,
                    "--truth-map",
                    truth,
                    "--canonical-links",
                    canonical,
                    "--hard-negatives",
                    hard_negatives,
                    "--output-dir",
                    destination,
                    "--scope",
                    "final",
                ),
                (destination / "mct_evaluation.json", destination / "labelled_test_set.csv.gz"),
            )
        )

    steps.extend(
        [
            PipelineStep(
                "compare_mct_models",
                "Select the model family using the frozen validation policy.",
                _module(
                    "src.evaluation.compare_mct_models",
                    "--heuristic",
                    scoring / "mct_evaluation.json",
                    "--fellegi-sunter",
                    fs / "mct_evaluation.json",
                    "--logistic",
                    logistic / "mct_evaluation.json",
                    "--output-dir",
                    logistic,
                ),
                (logistic / "logistic_comparison.json",),
            ),
            PipelineStep(
                "cluster_heuristic_baseline",
                "Form the heuristic baseline components and apply Rule 1.",
                _module(
                    "src.clustering.cluster_records",
                    "--normalized-path",
                    normalized,
                    "--scored-path",
                    heuristic_scores,
                    "--output-dir",
                    heuristic_clusters,
                ),
                (heuristic_clusters / "cluster_assignments.csv.gz", heuristic_clusters / "clustering_manifest.json"),
            ),
            PipelineStep(
                "evaluate_heuristic_clusters",
                "Evaluate heuristic components after Rule 1.",
                _module(
                    "src.evaluation.evaluate_clusters",
                    "--assignments",
                    heuristic_clusters / "cluster_assignments.csv.gz",
                    "--clustering-manifest",
                    heuristic_clusters / "clustering_manifest.json",
                    "--truth-map",
                    truth,
                    "--canonical-links",
                    canonical,
                    "--hard-negatives",
                    hard_negatives,
                    "--output-dir",
                    heuristic_clusters,
                ),
                (heuristic_clusters / "cluster_evaluation.json",),
            ),
            PipelineStep(
                "cluster_logistic_challenger",
                "Form logistic challenger components and apply Rule 1.",
                _module(
                    "src.clustering.cluster_records",
                    "--normalized-path",
                    normalized,
                    "--scored-path",
                    logistic_scores,
                    "--output-dir",
                    clusters,
                ),
                (clusters / "cluster_assignments.csv.gz", clusters / "clustering_manifest.json"),
            ),
            PipelineStep(
                "evaluate_logistic_clusters",
                "Evaluate logistic components, hard negatives and Rule 1 quarantine.",
                _module(
                    "src.evaluation.evaluate_clusters",
                    "--assignments",
                    clusters / "cluster_assignments.csv.gz",
                    "--clustering-manifest",
                    clusters / "clustering_manifest.json",
                    "--truth-map",
                    truth,
                    "--canonical-links",
                    canonical,
                    "--hard-negatives",
                    hard_negatives,
                    "--output-dir",
                    clusters,
                ),
                (clusters / "cluster_evaluation.json",),
            ),
        ]
    )
    if complete_release:
        steps.extend(
            [
                PipelineStep(
                    "compare_cluster_models",
                    "Require every cluster-level safety and promotion gate to pass.",
                    _module(
                        "src.evaluation.compare_cluster_models",
                        "--baseline-dir",
                        heuristic_clusters,
                        "--challenger-dir",
                        clusters,
                        "--output-dir",
                        clusters,
                    ),
                    (clusters / "cluster_comparison.json",),
                ),
                PipelineStep(
                    "consolidate_evaluation",
                    "Build frozen-test subgroup, calibration and error-analysis reports.",
                    _module(
                        "src.evaluation.consolidate_evaluation",
                        "--labelled-dir",
                        logistic,
                        "--normalized",
                        normalized,
                        "--blocking-evaluation",
                        blocking / "blocking_evaluation.json",
                        "--scoring-evaluation",
                        logistic / "mct_evaluation.json",
                        "--scoring-manifest",
                        logistic / "logistic_manifest.json",
                        "--cluster-evaluation",
                        clusters / "cluster_evaluation.json",
                        "--clustering-manifest",
                        clusters / "clustering_manifest.json",
                        "--output-dir",
                        evaluation,
                    ),
                    (evaluation / "evaluation_summary.json", evaluation / "evaluation_report.md"),
                ),
                PipelineStep(
                    "estimate_business_count",
                    "Estimate customer count and review workload without operationally merging uncertain edges.",
                    _module(
                        "src.business.estimate_customers",
                        "--data-dir",
                        data_dir,
                        "--assignments",
                        clusters / "cluster_assignments.csv.gz",
                        "--selected-scores",
                        logistic_scores,
                        "--frozen-test-labels",
                        logistic / "labelled_test_set.csv.gz",
                        "--phase12-summary",
                        evaluation / "evaluation_summary.json",
                        "--output-dir",
                        business,
                    ),
                    (business / "business_estimate.json", business / "business_estimate.md"),
                ),
                PipelineStep(
                    "evaluate_business_count",
                    "Evaluate the frozen business estimate against hidden synthetic truth.",
                    _module(
                        "src.evaluation.evaluate_business_estimate",
                        "--estimate",
                        business / "business_estimate.json",
                        "--classifications",
                        business / "observable_traffic_records.csv.gz",
                        "--truth-map",
                        truth,
                        "--output-dir",
                        business,
                    ),
                    (business / "business_estimate_evaluation.json",),
                ),
            ]
        )
    if include_tests:
        steps.append(
            PipelineStep(
                "repository_tests",
                "Run the complete automated regression suite.",
                _module("unittest", "discover", "-s", "tests", "-v"),
            )
        )
    return steps


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    payload = json.dumps(manifest, indent=2) + "\n"
    last_error: PermissionError | None = None
    for attempt in range(MANIFEST_WRITE_ATTEMPTS):
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt + 1 < MANIFEST_WRITE_ATTEMPTS:
                time.sleep(min(0.05 * (2**attempt), 0.8))
    raise PipelineError(
        f"Unable to update run manifest after {MANIFEST_WRITE_ATTEMPTS} attempts: "
        f"{last_error}. A sync or antivirus process may be locking {path}; use --run-dir "
        "outside the synchronized folder."
    ) from last_error


def _check_sources(data_dir: Path) -> None:
    missing = [name for name in REQUIRED_SOURCE_FILES if not (data_dir / name).is_file()]
    if missing:
        raise PipelineError(f"Existing dataset is incomplete; missing: {', '.join(missing)}")


def _prepare_run_directory(run_dir: Path) -> None:
    if run_dir == PROJECT_ROOT or PROJECT_ROOT in run_dir.parents and run_dir.name in {"data", "outputs"}:
        raise PipelineError("Run directory must not be the repository root or a committed data/output directory")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise PipelineError(f"Run directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)


def _run_step(command: Sequence[str]) -> subprocess.CompletedProcess[Any]:
    """Execute one stage through a narrow seam that tests can replace safely."""

    return subprocess.run(command, cwd=PROJECT_ROOT, check=False)


def execute_pipeline(args: argparse.Namespace) -> Path:
    mode = args.mode
    generate = mode != "existing"
    scale = 0.1 if mode == "small" else 1.0
    if args.scale is not None:
        if mode == "existing":
            raise PipelineError("--scale cannot be used with --mode existing")
        scale = args.scale
    if not 0 < scale <= 1:
        raise PipelineError("--scale must be greater than 0 and at most 1")

    run_dir = _absolute(args.run_dir or _default_run_dir(mode)).resolve()
    data_dir = (
        _absolute(args.data_dir).resolve()
        if mode == "existing"
        else run_dir / "data" / "generated"
    )
    output_dir = run_dir / "outputs"
    if mode == "existing":
        _check_sources(data_dir)

    report_scale = scale
    if mode == "existing":
        try:
            report = json.loads((data_dir / "generation_report.json").read_text(encoding="utf-8"))
            report_scale = float(report["generation_parameters"]["scale"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PipelineError(f"Unable to determine existing dataset scale: {exc}") from exc
    include_compliance_audit = abs(report_scale - 1.0) < 1e-12
    complete_release = include_compliance_audit

    steps = build_steps(
        data_dir,
        output_dir,
        generate=generate,
        scale=scale,
        seed=args.seed,
        include_compliance_audit=include_compliance_audit,
        complete_release=complete_release,
        include_tests=not args.skip_tests,
    )
    if args.dry_run:
        print(f"Mode: {mode}; scale: {scale}; run directory: {run_dir}")
        for index, step in enumerate(steps, 1):
            print(f"{index:02d}. {step.name}: {subprocess.list2cmdline(step.command)}")
        return run_dir

    _prepare_run_directory(run_dir)
    manifest_path = run_dir / "pipeline_run_manifest.json"
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "mode": mode,
        "scale": scale,
        "dataset_report_scale": report_scale,
        "strict_full_scale_audit_included": include_compliance_audit,
        "complete_release_pipeline": complete_release,
        "seed": args.seed,
        "started_at_utc": _utc_now(),
        "finished_at_utc": None,
        "run_directory": str(run_dir),
        "data_directory": str(data_dir),
        "output_directory": str(output_dir),
        "environment": {
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
        "steps": [],
    }
    _write_manifest(manifest_path, manifest)
    total = len(steps)
    overall_start = time.monotonic()
    try:
        for index, step in enumerate(steps, 1):
            print(f"\n[{index}/{total}] {step.name}: {step.description}", flush=True)
            print(f"$ {subprocess.list2cmdline(step.command)}", flush=True)
            record: dict[str, Any] = {
                "name": step.name,
                "description": step.description,
                "status": "running",
                "command": list(step.command),
                "started_at_utc": _utc_now(),
                "finished_at_utc": None,
                "duration_seconds": None,
                "return_code": None,
                "artifacts": [],
            }
            manifest["steps"].append(record)
            _write_manifest(manifest_path, manifest)
            step_start = time.monotonic()
            completed = _run_step(step.command)
            record["return_code"] = completed.returncode
            record["duration_seconds"] = round(time.monotonic() - step_start, 3)
            record["finished_at_utc"] = _utc_now()
            if completed.returncode != 0:
                record["status"] = "failed"
                raise PipelineError(f"Step {step.name} returned exit code {completed.returncode}")
            missing = [path for path in step.expected_outputs if not path.is_file()]
            if missing:
                record["status"] = "failed"
                raise PipelineError(
                    f"Step {step.name} did not create required artifacts: "
                    + ", ".join(str(path) for path in missing)
                )
            if step.name == "compare_mct_models":
                try:
                    comparison = json.loads(
                        (output_dir / "logistic" / "logistic_comparison.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    selected_model = comparison["selected_model"]
                except (OSError, KeyError, json.JSONDecodeError) as exc:
                    record["status"] = "failed"
                    raise PipelineError(f"Unable to read model-selection result: {exc}") from exc
                record["selected_model"] = selected_model
                manifest["selected_model"] = selected_model
                if complete_release and selected_model != "logistic_regression_mct":
                    record["status"] = "failed"
                    raise PipelineError(
                        "The full release contract expects logistic_regression_mct, but "
                        f"validation selected {selected_model}"
                    )
            record["artifacts"] = [_artifact(path, run_dir) for path in step.expected_outputs]
            record["status"] = "passed"
            _write_manifest(manifest_path, manifest)
        manifest["status"] = "passed"
    except (OSError, PipelineError) as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        raise
    finally:
        manifest["finished_at_utc"] = _utc_now()
        manifest["duration_seconds"] = round(time.monotonic() - overall_start, 3)
        _write_manifest(manifest_path, manifest)

    print(f"\nPIPELINE PASSED in {manifest['duration_seconds']:.1f}s")
    print(f"Run manifest: {manifest_path}")
    if complete_release:
        print(f"Business report: {output_dir / 'business' / 'business_estimate.md'}")
    else:
        print("Scope: small-scale engineering/model smoke test; final business release was not recalculated")
    return run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("small", "full", "existing"),
        default="small",
        help="small generates 10%% data; full generates 100%%; existing reuses --data-dir",
    )
    parser.add_argument("--scale", type=float, help="Override generation scale for small/full")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-dir", type=Path, default=Path("data/generated"))
    parser.add_argument("--run-dir", type=Path, help="Fresh isolated run directory")
    parser.add_argument("--skip-tests", action="store_true", help="Skip the final repository test suite")
    parser.add_argument("--dry-run", action="store_true", help="Print the execution plan without writing files")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        execute_pipeline(args)
    except PipelineError as exc:
        print(f"[pipeline] ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
