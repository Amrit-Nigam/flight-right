"""Audit exact decoded audio overlap; does not use test transcripts for tuning."""
from __future__ import annotations
import hashlib
import argparse
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional output file; archived studies are not recreated by default")
    args = parser.parse_args()
    from ml_pipeline.voice.train_whisper import all_rows
    from ml_pipeline.voice.build_audio_cache import CACHE, SR
    rows = all_rows()
    selected = rows[rows.split.isin(["train", "val", "test"])]
    bins, seen, collisions = {}, {}, []
    for row in selected.itertuples():
        name = getattr(row, "bin", None)
        name = name if isinstance(name, str) and name else "audio_int16.bin"
        if name not in bins:
            bins[name] = np.memmap(CACHE / name, dtype=np.int16, mode="r")
        start, length = int(row.offset), int(row.n_samples)
        assert 0 <= start < start + length <= len(bins[name]), row.uid
        assert 0 < length <= 30 * SR, row.uid
        digest = hashlib.sha256(bins[name][start:start + length].tobytes()).hexdigest()
        item = {"uid": row.uid, "corpus": row.corpus, "split": row.split}
        previous = seen.setdefault(digest, item)
        if previous["split"] != row.split:
            collisions.append({"first": previous, "second": item, "sha256": digest})
    report = {"clips_checked": len(selected), "distinct_exact_waveforms": len(seen),
              "cross_split_exact_duplicates": collisions,
              "limits": "Checks identical decoded PCM only, not near duplicates or shared unknown speakers. Test transcripts are not read for selection."}
    out = args.output or ROOT / "ml_pipeline/reports/voice_tuning_20261110/data_audit.json"
    if args.output is not None or out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if collisions:
        raise SystemExit("Cross-split duplicates require review before reporting new results")


if __name__ == "__main__":
    main()
