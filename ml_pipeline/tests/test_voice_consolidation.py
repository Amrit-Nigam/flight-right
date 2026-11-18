"""Speech deployment defaults, lossless archive reads and publication regression checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import consolidate_evaluations as ev
from server.app.config import _default_speech_model


class VoiceConsolidationTests(unittest.TestCase):
    def test_complete_latest_model_selected_with_previous_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            latest, previous = Path(tmp) / "new", Path(tmp) / "previous"
            latest.mkdir()
            self.assertEqual(_default_speech_model(latest, previous), previous)
            for name in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"):
                (latest / name).touch()
            self.assertEqual(_default_speech_model(latest, previous), latest)
            (latest / "tokenizer.json").unlink()
            self.assertEqual(_default_speech_model(latest, previous), previous)

    def test_family_and_checkpoints_remain_distinct(self):
        for model in ("C:/voice/models/uniform_soup3", "C:/voice/ct2/local__uniform_soup3__int8_float16",
                      "C:/voice/flightright-whisper-small-atc-p1"):
            self.assertEqual(ev.asr_key(model), "asr_small_atc_p1")
        self.assertEqual(ev.speech_checkpoint("C:/voice/ct2/local__uniform_soup3__int8_float16"), "uniform_soup3")
        self.assertNotEqual(ev.speech_checkpoint("C:/voice/flightright-whisper-small-atc-p1"), "uniform_soup3")
        self.assertEqual(ev.asr_key("openai/whisper-small"), "asr_small")

    def test_deleted_binary_evidence_round_trip_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.bin"
            source.write_bytes(b"\xff\x00\r\nrecorded evidence")
            with patch.object(ev, "ROOT", root):
                record = ev.make_record(source)
                source.unlink()
                with patch.object(ev, "records_all", return_value={"input.bin": record}):
                    self.assertEqual(ev.read_evidence("input.bin"), b"\xff\x00\r\nrecorded evidence")
                    record["sha256"] = "0" * 64
                    with self.assertRaises(AssertionError):
                        ev.read_evidence("input.bin")

    def test_publisher_shows_selected_speech_and_replaces_obsolete_summary(self):
        # Run the real publisher against isolated output, using the real preserved evidence.
        records = ev.records_all()
        family = ev.read_ledger("asr_small_atc_p1")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            with patch.object(ev, "ROOT", root), patch.object(ev, "records_all", return_value=records), \
                 patch.object(ev, "read_ledger", return_value=family):
                ev.refresh()
            text = (root / "docs/evaluation.md").read_text(encoding="utf-8")
            self.assertIn("| uniform_soup3 | served default | atco2_clean | 2026-11-10 | 762 | 27.95 |", text)
            self.assertNotIn("| flightright-whisper-small-atc-p1 |", text)
            self.assertNotIn("28.29", text)
            self.assertNotIn("| Served residual LSTM |", text)
            self.assertNotIn("| Served archive + destination |", text)
            self.assertNotIn("No completed P2/accent model", text)
            destination = root / "docs/evaluation.md"
            prefix = b"# Historical comparison\r\n\r\nOld numbers: 123.456\r\n"
            destination.write_bytes(prefix)
            with patch.object(ev, "ROOT", root), patch.object(ev, "records_all", return_value=records), \
                 patch.object(ev, "read_ledger", return_value=family):
                ev.refresh()
                first = destination.read_bytes()
                self.assertNotIn(b"Old numbers: 123.456", first)
                self.assertEqual(first.decode("utf-8"), text)
                headings = [line for line in text.splitlines() if line.startswith("## ")]
                self.assertEqual(len(headings), len(set(headings)))
                ev.refresh()
                self.assertEqual(destination.read_bytes(), first)

    def test_ledger_appends_capsules_and_rejects_history_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            key = "asr_small"
            original = {"model": key, "records": []}
            prefix = ("# Original history\r\nKeep these numbers: 12.345\r\n\n" + ev.MARK +
                      json.dumps(original) + "\n```\n").encode()
            path = out / (key + ".md")
            path.write_bytes(prefix)
            payload = {"model": key, "records": [], "verification_runs": [
                {"id": "check1", "narrative_markdown": "## Verified change\n\nNew evidence."}]}
            with patch.object(ev, "OUT", out):
                ev.write_ledger(key, payload)
                first = path.read_bytes()
                self.assertTrue(first.startswith(prefix))
                self.assertEqual(ev.read_ledger(key), payload)
                ev.write_ledger(key, payload)
                self.assertEqual(path.read_bytes(), first)
                with self.assertRaises(AssertionError):
                    ev.write_ledger(key, original)


if __name__ == "__main__":
    unittest.main()
