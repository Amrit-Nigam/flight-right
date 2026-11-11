"""Checks for dropped training tails, failed producers and validation-only selection."""
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import torch
from ml_pipeline.voice.blend_whisper import average_into
from ml_pipeline.voice.train_whisper import accumulation_group_size, update_boundary, batches
from ml_pipeline.voice.transcribe import ct2_path
from scripts.experiment_voice_tuning import choose, freeze_selection


class VoiceTrainingTests(unittest.TestCase):
    def test_weight_average_preserves_ties_and_unchanged_tensors(self):
        shared = torch.zeros(2)
        other = torch.zeros(1)
        model = SimpleNamespace(state_dict=lambda: {"shared": shared, "alias": shared, "other": other})
        readers = [SimpleNamespace(get_tensor=lambda key, n=n: {"shared": torch.tensor([n, n + 2.]),
                                                               "other": torch.tensor([2.])}[key])
                   for n in (1., 3., 5.)]
        self.assertEqual(average_into(model, readers), (1, 1))
        torch.testing.assert_close(shared, torch.tensor([3., 5.]))
        self.assertTrue(torch.equal(other, torch.tensor([2.])))

    def test_unaligned_average_is_rejected(self):
        model = SimpleNamespace(state_dict=lambda: {"weight": torch.zeros(2)})
        readers = [SimpleNamespace(get_tensor=lambda key: torch.zeros(3))]
        with self.assertRaisesRegex(ValueError, "Unaligned source tensor"):
            average_into(model, readers)

    def test_selection_timestamp_and_winner_remain_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "selection.json"
            original = dict(winner="baseline", model="model", validation={"baseline": {"a": 10}},
                            frozen_utc="initial")
            freeze_selection(path, original)
            self.assertEqual(freeze_selection(path, dict(original, frozen_utc="later")), original)
            with self.assertRaisesRegex(RuntimeError, "Frozen validation choice changed"):
                freeze_selection(path, dict(original, winner="other"))

    def test_ready_runtime_model_does_not_need_reconversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            for name in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"):
                (path / name).touch()
            self.assertEqual(ct2_path(str(path), "int8_float16"), path.resolve())

    def test_incomplete_runtime_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "model.bin").touch()
            with self.assertRaisesRegex(RuntimeError, "Incomplete runtime model"):
                ct2_path(tmp, "int8_float16")

    def test_tail_has_correct_loss_scale_and_is_updated(self):
        for count in range(1, 12):
            for accumulation in range(1, 5):
                sizes = [accumulation_group_size(i, count, accumulation) for i in range(count)]
                self.assertAlmostEqual(sum(1 / n for n in sizes),
                                       (count + accumulation - 1) // accumulation)
                self.assertEqual(sizes[-1], (count - 1) % accumulation + 1)
                updates = [i for i in range(count) if update_boundary(i, count, accumulation)]
                self.assertEqual(len(updates), (count + accumulation - 1) // accumulation)
                self.assertEqual(updates[-1], count - 1)

    def test_audio_failure_reaches_consumer(self):
        def bad_audio(row):
            raise ValueError("damaged recording")
        with self.assertRaisesRegex(ValueError, "damaged recording"):
            list(batches(pd.DataFrame({"text": ["hello"]}), [0], bad_audio,
                         SimpleNamespace(feature_extractor=lambda *a, **k: None), 1))

    def test_winner_cannot_trade_large_corpus_regression_for_mean(self):
        scores = {"baseline": {"atcosim": 10, "uwb": 20},
                  "bad_trade": {"atcosim": 11, "uwb": 10},
                  "better": {"atcosim": 9, "uwb": 19}}
        self.assertEqual(choose(scores), "better")

    def test_baseline_retained_when_candidates_are_worse(self):
        self.assertEqual(choose({"baseline": {"a": 5, "b": 10},
                                 "candidate": {"a": 6, "b": 11}}), "baseline")


if __name__ == "__main__":
    unittest.main()
