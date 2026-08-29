from __future__ import annotations

import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from src.clustering.cluster_records import ASSIGNMENT_COLUMNS, cluster_records
from src.clustering.rules import DEFAULT_RULES, UnionFind, component_status, load_clustering_rules
from src.evaluation.evaluate_clusters import evaluate_clusters
from src.scoring.score_candidates import SCORE_COLUMNS


def make_clustering_fixture(root: Path) -> tuple[Path, Path]:
    normalized = root / "normalized.csv.gz"
    with gzip.open(normalized, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source", "record_ordinal", "source_record_id"],
        )
        writer.writeheader()
        for ordinal in range(1, 27):
            writer.writerow(
                {
                    "source": "system",
                    "record_ordinal": ordinal,
                    "source_record_id": f"R{ordinal}",
                }
            )
    scored = root / "scored.csv.gz"
    with gzip.open(scored, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCORE_COLUMNS)
        writer.writeheader()

        def edge(left: int, right: int, score: float, decision: str) -> None:
            writer.writerow(
                {
                    "left_source": "system",
                    "left_record_ordinal": left,
                    "left_source_record_id": f"R{left}",
                    "right_source": "system",
                    "right_record_ordinal": right,
                    "right_source_record_id": f"R{right}",
                    "blocking_rules": "exact_email",
                    "positive_evidence": "exact_verified_email",
                    "evidence_family_count": 1,
                    "conflicts": "",
                    "positive_score": f"{score:.6f}",
                    "conflict_penalty": "0.000000",
                    "mct_score": f"{score:.6f}",
                    "decision": decision,
                }
            )

        for ordinal in range(1, 12):
            edge(ordinal, ordinal + 1, 0.90, "auto_merge")
        for ordinal in range(13, 25):
            edge(ordinal, ordinal + 1, 0.90, "auto_merge")
        edge(12, 26, 0.82, "human_review")
    return normalized, scored


class ClusteringRuleTests(unittest.TestCase):
    def test_rule1_accepts_12_and_quarantines_13(self) -> None:
        rules = load_clustering_rules(DEFAULT_RULES)
        self.assertEqual(rules["maximum_accepted_source_records"], 12)
        self.assertEqual(component_status(12), "accepted_merged")
        self.assertEqual(component_status(13), "quarantined_oversized")

    def test_union_find_is_transitive(self) -> None:
        union_find = UnionFind(4)
        union_find.union(0, 1)
        union_find.union(1, 2)
        self.assertEqual(union_find.find(0), union_find.find(2))
        self.assertNotEqual(union_find.find(0), union_find.find(3))


class ClusteringPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.normalized, cls.scored = make_clustering_fixture(cls.root)
        cls.output = cls.root / "output"
        cls.manifest = cluster_records(cls.normalized, cls.scored, cls.output, show_progress=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_oversized_component_is_rejected_in_full_without_partial_merge(self) -> None:
        self.assertEqual(self.manifest["total_source_records"], 26)
        self.assertEqual(self.manifest["proposed_component_count"], 3)
        self.assertEqual(self.manifest["accepted_merged_component_count"], 1)
        self.assertEqual(self.manifest["accepted_singleton_count"], 1)
        self.assertEqual(self.manifest["quarantined_component_count"], 1)
        self.assertEqual(self.manifest["quarantined_record_count"], 13)
        self.assertEqual(self.manifest["rejected_auto_merge_edges"], 12)
        self.assertEqual(self.manifest["partial_merges_from_quarantined_components"], 0)
        self.assertEqual(self.manifest["threshold_adjustments_for_rule1"], 0)
        self.assertEqual(self.manifest["final_resolved_identity_count"], 15)

        with gzip.open(
            self.output / "cluster_assignments.csv.gz", "rt", encoding="utf-8", newline=""
        ) as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(set(rows[0]), set(ASSIGNMENT_COLUMNS))
        accepted_12 = [row for row in rows if 1 <= int(row["record_ordinal"]) <= 12]
        quarantined_13 = [row for row in rows if 13 <= int(row["record_ordinal"]) <= 25]
        self.assertEqual(len({row["final_cluster_id"] for row in accepted_12}), 1)
        self.assertTrue(all(row["final_cluster_id"] for row in accepted_12))
        self.assertTrue(all(not row["final_cluster_id"] for row in quarantined_13))
        self.assertTrue(all(row["cluster_status"] == "quarantined_oversized" for row in quarantined_13))

    def test_review_edge_does_not_join_components(self) -> None:
        self.assertEqual(self.manifest["scored_pair_decision_counts"]["human_review"], 1)
        self.assertEqual(self.manifest["accepted_singleton_count"], 1)
        self.assertFalse(self.manifest["phase_boundaries"]["human_review_pairs_merged"])

    def test_assignment_output_is_deterministic(self) -> None:
        second_output = self.root / "output-second"
        second = cluster_records(self.normalized, self.scored, second_output, show_progress=False)
        self.assertEqual(
            self.manifest["assignment_output"]["sha256"],
            second["assignment_output"]["sha256"],
        )
        self.assertEqual(
            (self.output / "cluster_assignments.csv.gz").read_bytes(),
            (second_output / "cluster_assignments.csv.gz").read_bytes(),
        )

    def test_production_clusterer_has_no_label_dependency(self) -> None:
        source = Path("src/clustering/cluster_records.py").read_text(encoding="utf-8")
        for forbidden in (
            "person_map.csv",
            "canonical_duplicate_links.jsonl",
            "hard_negatives.json",
            "person_id",
            "truth_key",
            "scenario_type",
            "evidence_mode",
        ):
            self.assertNotIn(forbidden, source)


class ClusterEvaluationTests(unittest.TestCase):
    def test_cluster_precision_recall_and_quarantine_contents_are_measured_afterward(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            normalized, scored = make_clustering_fixture(root)
            output = root / "output"
            cluster_records(normalized, scored, output, show_progress=False)
            truth = root / "person_map.csv"
            with truth.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("system", "record_id", "person_id", "entity_type"))
                for ordinal in range(1, 27):
                    person = "P1" if ordinal <= 12 else "P2" if ordinal <= 25 else "P3"
                    writer.writerow(("system", f"R{ordinal}", person, "human"))
            canonical = root / "canonical.jsonl"
            canonical.write_text(
                "\n".join(
                    json.dumps(item)
                    for item in (
                        {
                            "source_system_a": "system", "source_record_id_a": "R1",
                            "source_system_b": "system", "source_record_id_b": "R12",
                            "intended_recoverability": True,
                        },
                        {
                            "source_system_a": "system", "source_record_id_a": "R13",
                            "source_system_b": "system", "source_record_id_b": "R25",
                            "intended_recoverability": True,
                        },
                    )
                ) + "\n",
                encoding="utf-8",
            )
            hard = root / "hard.json"
            hard.write_text(
                json.dumps(
                    [
                        {
                            "type": "different_people",
                            "source_records": [
                                {"system": "system", "record_id": "R1"},
                                {"system": "system", "record_id": "R26"},
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            result = evaluate_clusters(
                output / "cluster_assignments.csv.gz",
                output / "clustering_manifest.json",
                truth,
                canonical,
                hard,
                output,
            )
            pairwise = result["pairwise_cluster_metrics"]
            self.assertEqual(pairwise["predicted_merged_pairs"], 66)
            self.assertEqual(pairwise["true_positive_merged_pairs"], 66)
            self.assertEqual(pairwise["false_positive_merged_pairs"], 0)
            self.assertEqual(pairwise["precision"], 1.0)
            self.assertAlmostEqual(pairwise["recall_humans"], 66 / 144)
            self.assertEqual(result["canonical_link_metrics"]["accepted_cluster_links"], 1)
            self.assertEqual(result["canonical_link_metrics"]["quarantined_together_links"], 1)
            self.assertEqual(result["hard_negative_metrics"]["co_clustered_after_transitivity"], 0)
            self.assertEqual(result["quarantine_evaluation"]["record_count"], 13)
            self.assertEqual(result["quarantine_evaluation"]["distinct_hidden_entities"], 1)
            self.assertTrue(result["isolation"]["labels_used_after_clustering_only"])


if __name__ == "__main__":
    unittest.main()
