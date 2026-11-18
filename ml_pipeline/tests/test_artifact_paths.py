"""Shared inputs must preserve historical bytes and isolated data roots."""
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ml_pipeline import artifact_paths as artifacts


class ArtifactReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.patches = [patch.object(artifacts, "ROOT", self.root),
                        patch.object(artifacts, "REGISTRY", self.root / "registry.json")]
        for p in self.patches:
            p.start()
        self.canonical = self.root / "shared/model.bin"
        self.canonical.parent.mkdir()
        self.canonical.write_bytes(b"recorded weights")
        self.alias = self.root / "old-run/model.bin"

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_reference_keeps_only_canonical_bytes(self):
        artifacts.register_reference(self.alias, self.canonical)
        self.assertFalse(self.alias.exists())
        self.assertEqual(artifacts.resolve_artifact(self.alias), self.canonical)

    def test_old_study_rejects_changed_model_even_when_filename_is_same(self):
        artifacts.register_reference(self.alias, self.canonical)
        self.canonical.write_bytes(b"new model weights")
        with self.assertRaisesRegex(ValueError, "Shared artifact changed"):
            artifacts.resolve_artifact(self.alias)

    def test_old_study_rejects_missing_model(self):
        artifacts.register_reference(self.alias, self.canonical)
        self.canonical.unlink()
        with self.assertRaises(FileNotFoundError):
            artifacts.resolve_artifact(self.alias)

    def test_isolated_external_data_root_is_not_redirected(self):
        outside = self.root.parent / "isolated-smoke-test/trajectory_test.npz"
        self.assertEqual(artifacts.resolve_artifact(outside), outside)

    def test_registry_cannot_escape_project(self):
        artifacts.REGISTRY.write_text(json.dumps({"aliases": {
            "old-run/model.bin": {"canonical": "../outside.bin", "sha256": "invalid"}}}))
        with self.assertRaises(ValueError):
            artifacts.resolve_artifact(self.alias)

    def test_distinct_output_is_never_discarded(self):
        artifacts.register_reference(self.alias, self.canonical)
        output = self.root / "new.bin"
        output.write_bytes(b"different model")
        self.assertEqual(artifacts.reuse_identical_output(output), output)
        self.assertTrue(output.exists())

    def test_generated_identical_export_is_replaced_with_reference(self):
        artifacts.register_reference(self.alias, self.canonical)
        self.alias.parent.mkdir()
        self.alias.write_bytes(self.canonical.read_bytes())
        self.assertEqual(artifacts.reuse_identical_output(self.alias), self.canonical)
        self.assertFalse(self.alias.exists())
        self.assertEqual(artifacts.resolve_artifact(self.alias), self.canonical)

    def test_existing_alias_file_is_not_overwritten(self):
        self.alias.parent.mkdir()
        self.alias.write_bytes(b"distinct experiment")
        with self.assertRaises(FileExistsError):
            artifacts.register_reference(self.alias, self.canonical)
        self.assertEqual(self.alias.read_bytes(), b"distinct experiment")

    def test_retraining_cannot_silently_reuse_an_old_studys_alias(self):
        artifacts.register_reference(self.alias, self.canonical)
        self.alias.parent.mkdir()
        self.alias.write_bytes(b"newly trained different weights")
        with self.assertRaisesRegex(ValueError, "use a new run path"):
            artifacts.reuse_identical_output(self.alias)
        self.assertTrue(self.alias.exists())

    def test_audited_raw_export_uses_packaged_hash_without_confusing_provenance(self):
        raw = b"original model export"
        self.canonical.write_bytes(raw + b" plus model card")
        registry = {"schema": 1, "aliases": {"old-run/model.bin": {
            "canonical": "shared/model.bin", "sha256": artifacts.checksum(self.canonical),
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "relationship": "same_bundle_plus_tuning_model_card"}}}
        artifacts.REGISTRY.write_text(json.dumps(registry))
        self.alias.parent.mkdir()
        self.alias.write_bytes(raw)
        self.assertEqual(artifacts.resolve_artifact(self.alias), self.canonical)
        self.assertEqual(artifacts.reuse_identical_output(self.alias), self.canonical)
        self.assertFalse(self.alias.exists())


class ExplicitArchiveInputsTests(unittest.TestCase):
    def test_explicit_files_match_default_preprocessing(self):
        import os
        import sys
        import pandas as pd
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training/trajectory"))
        import preprocess_sequences as pre
        frame = pd.DataFrame({"icao24": ["a", "a", "b"], "time_position": [2, 1, 1],
                              "on_ground": [False, False, True], "latitude": [19.] * 3,
                              "longitude": [72.] * 3, "baro_altitude": [1000.] * 3,
                              "velocity": [100.] * 3, "true_track": [90.] * 3})
        with patch.dict(os.environ, {}, clear=True), patch.object(pre.glob, "glob", return_value=["original.parquet"]), patch.object(pre.pd, "read_parquet", return_value=frame) as read:
            expected = pre.load_valid_states()
            actual = pre.load_valid_states(paths=["original.parquet"])
            pd.testing.assert_frame_equal(actual, expected)
            self.assertEqual(read.call_args.args[0], "original.parquet")

    def test_empty_explicit_cohort_does_not_read_unrelated_training_data(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training/trajectory"))
        import preprocess_sequences as pre
        with self.assertRaises(FileNotFoundError):
            pre.load_valid_states(paths=[])


if __name__ == "__main__":
    unittest.main()
