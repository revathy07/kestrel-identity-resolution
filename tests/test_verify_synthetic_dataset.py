import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_synthetic_dataset.py"
SPEC = importlib.util.spec_from_file_location("verify_synthetic_dataset", MODULE_PATH)
VERIFIER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = VERIFIER
SPEC.loader.exec_module(VERIFIER)


class VerifierUnitTests(unittest.TestCase):
    def test_recognises_all_mixed_timestamp_formats(self):
        examples = {
            "03-04-2026 12:30:00": "DD-MM-YYYY",
            "2026/04/03 12:30:00": "YYYY/MM/DD",
            "04-03-26 12:30": "MM-DD-YY",
            "2026-04-03T12:30:00+00:00": "ISO_OFFSET",
            "1775219400000": "EPOCH_MS",
            "2026-04-03 12:30:00": "LOCAL_TEXT",
        }
        for value, expected in examples.items():
            with self.subTest(value=value):
                self.assertEqual(VERIFIER.timestamp_format(value), expected)
                self.assertIsNotNone(VERIFIER.parse_timestamp(value))

    def test_exact_and_near_duplicate_counters(self):
        stats = VERIFIER.SourceStats()
        first = {"account_id": "1", "email": "a@example.test"}
        changed = {"account_id": "1", "email": "b@example.test"}
        VERIFIER.inspect_record("app_users", first, stats)
        VERIFIER.inspect_record("app_users", first, stats)
        VERIFIER.inspect_record("app_users", changed, stats)
        self.assertEqual(stats.exact_extra, 1)
        self.assertEqual(stats.near_extra, 1)

    def test_impossible_age_detection(self):
        self.assertTrue(VERIFIER.impossible_dob("2999-01-01"))
        self.assertTrue(VERIFIER.impossible_dob("1800-01-01"))
        self.assertFalse(VERIFIER.impossible_dob("1990-01-01"))

    def test_nested_metric_lookup(self):
        report = {"metrics": {"zero_evidence_duplicate_pair_rate": 0.08}}
        self.assertEqual(
            VERIFIER.find_numeric(report, {"zero_evidence_duplicate_pair_rate"}),
            0.08,
        )

    def test_nested_social_identity_payload_is_flattened(self):
        payload = (
            '[{"provider":"apple","identity_payload":'
            '{"provider_id":"apple_1","hashed_email":"abc"},'
            '"login_ts":"2026-04-03T12:30:00+00:00"}]'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "social.json"
            path.write_text(payload, encoding="utf-8")
            records = list(VERIFIER.iter_social(path))
        self.assertEqual(records[0]["provider_id"], "apple_1")
        self.assertEqual(records[0]["hashed_email"], "abc")
        self.assertNotIn("identity_payload", records[0])

    def test_nested_values_do_not_break_poison_scan(self):
        self.assertFalse(VERIFIER.record_has_poison({"identity_payload": {"provider_id": "x"}}))

    def test_missing_email_artifacts_never_create_naive_edges(self):
        for value in (None, "", "  ", '""', "null", "None", ' "quoted, comma"'):
            with self.subTest(value=value):
                self.assertFalse(VERIFIER.naive_tokens({"email": value}))


if __name__ == "__main__":
    unittest.main()
