"""Paired recording/speaker bootstrap AFTER selection; never chooses a model."""
from pathlib import Path
import json
import sys
import jiwer
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml_pipeline.voice.build_audio_cache import CACHE
from ml_pipeline.voice.evaluate_voice import gold_atco2
from ml_pipeline.voice.text_norm import normalise
from ml_pipeline.voice.transcribe import ASR_VERSION, _slug


def main():
    report = ROOT / "ml_pipeline/reports/voice_tuning_20261110"
    if not report.exists():
        from scripts.consolidate_evaluations import read_evidence
        print("Archived uncertainty estimates (no new inference or recomputation):")
        print(read_evidence(report / "uncertainty.json").decode("utf-8"))
        return
    selection = json.loads((report / "selection.json").read_text())
    assert (report / "test.json").exists(), "Finish frozen-choice testing first"
    old_path = CACHE / "transcripts/local__flightright-whisper-small-atc-p1__int8_float16.parquet"
    new_path = (old_path if selection["winner"] == "baseline" else
                ROOT / "checkpoints/voice_20261110/transcripts" / f"{_slug(selection['model'])}__int8_float16.parquet")
    def read(path):
        frame = pd.read_parquet(path)
        return frame[frame.asr_version == ASR_VERSION].set_index("uid")
    old, new = read(old_path), read(new_path)
    manifest = pd.read_parquet(CACHE / "manifest.parquet")
    gold = gold_atco2()
    cohorts = {"atco2_clean": gold[~gold.contaminated].assign(cluster=lambda f: f.recording)}
    for corpus in ("atcosim", "uwb"):
        cohorts[corpus] = manifest[(manifest.split == "test") & (manifest.corpus == corpus)].assign(cluster=lambda f: f.group)
    output = {"seed": 42, "resamples": 2000, "cohorts": {},
              "interpretation": "Retrospective descriptive intervals on repeatedly inspected historical tests. ATCOSIM has only three held-out speakers. Ordinary Indian English omitted: no speaker IDs for a reliable speaker-cluster interval. These intervals do not guarantee future gains."}
    for name, frame in cohorts.items():
        groups = {}
        for row in frame.itertuples():
            if not row.text:
                continue
            errors = []
            for predictions in (old, new):
                comparison = jiwer.process_words(row.text, normalise(predictions.loc[row.uid, "hyp"]))
                errors.append(comparison.substitutions + comparison.deletions + comparison.insertions)
            group = groups.setdefault(row.cluster, np.zeros(3, dtype=np.float64))
            group += [len(row.text.split()), *errors]
        array = np.stack(list(groups.values()))
        words, old_errors, new_errors = array.sum(axis=0)
        rng = np.random.default_rng(42)
        draws = array[rng.integers(0, len(array), size=(2000, len(array)))].sum(axis=1)
        differences = 100 * (draws[:, 2] - draws[:, 1]) / draws[:, 0]
        output["cohorts"][name] = {"clips": len(frame), "clusters": len(array),
            "reference_words": int(words), "previous_errors": int(old_errors), "selected_errors": int(new_errors),
            "word_error_change_percentage_points": round(float(100 * (new_errors - old_errors) / words), 4),
            "paired_cluster_95_percent_interval": np.percentile(differences, [2.5, 97.5]).round(4).tolist(),
            "negative_change_means_fewer_errors": True}
    (report / "uncertainty.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
