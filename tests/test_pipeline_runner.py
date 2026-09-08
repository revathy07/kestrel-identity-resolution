from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.run_pipeline import (
    PipelineError,
    _check_sources,
    _prepare_run_directory,
    _write_manifest,
    build_steps,
    execute_pipeline,
)


class PipelinePlanTests(unittest.TestCase):
    def test_small_plan_exercises_models_and_rule1_without_full_release_claims(self) -> None:
        root = Path("C:/isolated-run")
        steps = build_steps(
            root / "data/generated",
            root / "outputs",
            generate=True,
            scale=0.1,
            seed=42,
            include_compliance_audit=False,
            complete_release=False,
            include_tests=True,
        )
        names = [step.name for step in steps]
        self.assertEqual(len(names), 25)
        self.assertIn("generate_dataset", names)
        self.assertIn("compare_mct_models", names)
        self.assertIn("analyze_development_validation_recall_gaps", names)
        self.assertIn("cluster_logistic_challenger", names)
        self.assertIn("evaluate_logistic_clusters", names)
        self.assertIn("repository_tests", names)
        self.assertNotIn("dataset_compliance_audit", names)
        self.assertNotIn("compare_cluster_models", names)
        self.assertNotIn("estimate_business_count", names)

    def test_full_plan_contains_strict_audit_and_complete_release(self) -> None:
        root = Path("C:/isolated-run")
        steps = build_steps(
            root / "data/generated",
            root / "outputs",
            generate=True,
            scale=1.0,
            seed=42,
            include_compliance_audit=True,
            complete_release=True,
            include_tests=True,
        )
        names = [step.name for step in steps]
        self.assertEqual(len(names), 30)
        self.assertIn("dataset_compliance_audit", names)
        self.assertIn("compare_cluster_models", names)
        self.assertIn("consolidate_evaluation", names)
        self.assertIn("estimate_business_count", names)
        self.assertIn("evaluate_business_count", names)
        self.assertIn("analyze_development_validation_recall_gaps", names)

    def test_truth_release_and_training_order_is_explicit(self) -> None:
        root = Path("C:/isolated-run")
        names = [
            step.name
            for step in build_steps(
                root / "data/generated",
                root / "outputs",
                generate=True,
                scale=1.0,
                seed=42,
                include_compliance_audit=True,
                complete_release=True,
                include_tests=False,
            )
        ]
        self.assertLess(names.index("score_heuristic_mct"), names.index("release_development_labels"))
        self.assertLess(names.index("release_development_labels"), names.index("train_fellegi_sunter"))
        self.assertLess(names.index("release_validation_labels"), names.index("select_logistic_on_validation"))
        self.assertLess(names.index("select_logistic_on_validation"), names.index("evaluate_logistic_frozen_test"))
        self.assertLess(
            names.index("evaluate_logistic_frozen_test"),
            names.index("analyze_development_validation_recall_gaps"),
        )
        self.assertLess(
            names.index("analyze_development_validation_recall_gaps"),
            names.index("cluster_logistic_challenger"),
        )
        self.assertLess(names.index("compare_mct_models"), names.index("cluster_logistic_challenger"))


class PipelineSafetyTests(unittest.TestCase):
    def test_manifest_write_retries_a_transient_windows_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "pipeline_run_manifest.json"
            original_replace = Path.replace
            calls = 0

            def replace_after_one_lock(source: Path, target: Path) -> Path:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise PermissionError(5, "simulated sync lock")
                return original_replace(source, target)

            with patch.object(Path, "replace", new=replace_after_one_lock):
                with patch("scripts.run_pipeline.time.sleep") as sleeper:
                    _write_manifest(path, {"status": "running"})
            self.assertEqual(calls, 2)
            sleeper.assert_called_once()
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], "running")

    def test_nonempty_run_directory_is_rejected_without_deleting_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            run_dir.mkdir()
            marker = run_dir / "keep.txt"
            marker.write_text("user data", encoding="utf-8")
            with self.assertRaises(PipelineError):
                _prepare_run_directory(run_dir)
            self.assertEqual(marker.read_text(encoding="utf-8"), "user data")

    def test_existing_dataset_contract_lists_missing_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(PipelineError, "app_users.csv"):
                _check_sources(Path(temporary))

    def test_dry_run_does_not_create_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "dry-run"
            args = Namespace(
                mode="small",
                scale=None,
                seed=42,
                data_dir=Path("data/generated"),
                run_dir=run_dir,
                skip_tests=True,
                dry_run=True,
            )
            with redirect_stdout(io.StringIO()):
                result = execute_pipeline(args)
            self.assertEqual(result, run_dir.resolve())
            self.assertFalse(run_dir.exists())

    def test_failed_subprocess_is_recorded_and_pipeline_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "failed-run"
            args = Namespace(
                mode="small",
                scale=None,
                seed=42,
                data_dir=Path("data/generated"),
                run_dir=run_dir,
                skip_tests=True,
                dry_run=False,
            )
            with patch(
                "scripts.run_pipeline._run_step",
                return_value=subprocess.CompletedProcess([], 7),
            ) as mocked:
                with redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(PipelineError, "generate_dataset"):
                        execute_pipeline(args)
            self.assertEqual(mocked.call_count, 1)
            manifest = json.loads(
                (run_dir / "pipeline_run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "failed")
            self.assertEqual(manifest["steps"][0]["status"], "failed")
            self.assertEqual(manifest["steps"][0]["return_code"], 7)


if __name__ == "__main__":
    unittest.main()
