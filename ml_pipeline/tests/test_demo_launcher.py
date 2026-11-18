"""Bootstrap guards without installing packages, training or starting live services."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import start


class DemoLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.enterContext(patch.object(start, "ROOT", self.root))

    def test_manifest_rejects_paths_outside_checkout(self):
        for name in ("../other/model.bin", str(self.root.parent / "outside.bin")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                start.asset_path(name)

    def test_missing_and_changed_weights_fail_before_server_start(self):
        manifest = {"files": [{"path": "weights.bin", "bytes": 4, "sha256": "wrong"}]}
        for exists in (False, True):
            if exists:
                (self.root / "weights.bin").write_bytes(b"data")
            with self.assertRaisesRegex(RuntimeError, "Missing/changed"):
                start.verify_assets(manifest, download=False)

    def test_valid_asset_passes(self):
        path = self.root / "model.bin"
        path.write_bytes(b"model")
        start.verify_assets({"files": [{"path": "model.bin", "bytes": 5, "sha256": start.digest(path)}]})

    def test_lfs_pointer_is_not_treated_as_real_weights(self):
        path = self.root / "model.bin"
        path.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 5000\n")
        with self.assertRaises(RuntimeError):
            start.verify_assets({"files": [{"path": "model.bin", "bytes": 5000, "sha256": "abc"}]}, download=False)

    def test_replay_environment_is_self_contained_and_cpu(self):
        (self.root / "demo").mkdir()
        with patch.dict(start.os.environ, {"DATABASE_URL": "private-db", "FLIGHT_RIGHT_DATA_MODE": "live"}):
            env = start.environment("replay", {"speech_runtime": "model"})
        self.assertEqual(env["DATABASE_URL"], "")
        self.assertEqual(env["FLIGHT_RIGHT_DATA_MODE"], "replay")
        self.assertEqual(env["FLIGHT_RIGHT_ASR_DEVICE"], "cpu")
        self.assertEqual(env["FLIGHT_RIGHT_ROUTE_LOOKUP"], "off")
        self.assertTrue(Path(env["FLIGHT_RIGHT_AUDIT_DB"]).is_relative_to(self.root))
        self.assertEqual(env["FLIGHT_RIGHT_SPEECH_DEMO_DIR"], str(self.root / "demo/clips"))

    def test_no_install_does_not_create_venv(self):
        with self.assertRaisesRegex(RuntimeError, "environment is missing"):
            start.prepare_python(install=False)
        self.assertFalse((self.root / ".venv-demo").exists())

    def test_python_probe_checks_requested_environment(self):
        with patch.object(start.subprocess, "run", return_value=Mock(returncode=0, stdout='["torch"]')) as probe:
            self.assertFalse(start.requirements_satisfied(Path("chosen-python")))
        self.assertEqual(probe.call_args.args[0][0], "chosen-python")

    def test_frontend_does_not_install_in_no_install_mode(self):
        (self.root / "client").mkdir()
        (self.root / "client/package-lock.json").write_text("{}")
        with patch.object(start.shutil, "which", return_value="node"), patch.object(
                start.subprocess, "check_output", return_value="v22.19.0\n"):
            with self.assertRaisesRegex(RuntimeError, "npm ci"):
                start.prepare_frontend(install=False)


if __name__ == "__main__":
    unittest.main()
