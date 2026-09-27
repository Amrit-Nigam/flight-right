"""Decode every speech corpus once, and fix the train / validation / test split before training.

    python ml_pipeline/voice/build_audio_cache.py
    python ml_pipeline/voice/build_audio_cache.py --add svarah     # once the gate is accepted

Writes, under FLIGHT_RIGHT_VOICE_CACHE (default %LOCALAPPDATA%/FlightRight/voice, NOT the
OneDrive project folder, for the same reason the PostgreSQL data directory lives there):

    audio_int16.bin    every clip, 16 kHz mono int16, concatenated
    manifest.parquet   one row per clip: where it sits in the .bin, its transcript, its split

and a dated report in ml_pipeline/reports/.

THE SPLIT IS THE POINT OF THIS FILE (plan rule 1: split by speaker and recording session,
never randomly). It is written down here, before any training, so it cannot be tuned after.

- ATCOSIM (from the jlvdoorn mirror; filenames carry the speaker: ``sm3_01_042.wav``).
  Ten speakers. The mirror's own train/validation split puts the same speakers in both, so
  it is ignored. Test = one speaker from each of the three name groups, sm3, zf3, gm2
  (1,712 clips); validation = gm1, gf1 (516); train = sm1, sm2, sm4, zf1, zf2 (7,331).
- UWB-ATCC (Jzuluaga/uwb_atcc). No speaker identities, only recording ids
  (``ACCU-0agmXf``). The published train/test split is recording-disjoint apart from one
  recording, which is dropped from both sides. Validation = the train recordings whose id
  hashes to 0 mod 10.
- ATCO2 clips inside the jlvdoorn mirror are NOT used for training at all. That keeps the
  ATCO2 test set a genuine cross-corpus test for any model this project trains.
- ATCO2 1 h test set (Jzuluaga/atco2_corpus_1h): test only. The 109 clips that are the same
  audio as jlvdoorn training data (Phase 2.5) are flagged ``contaminated``; the other 762
  are the clean set.

Clips longer than 30 s (Whisper's window) or with an empty normalised transcript are kept in
the manifest with split ``excluded`` and a reason, so nothing disappears silently.
"""
from __future__ import annotations

import glob
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import librosa
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ml_pipeline.voice.text_norm import normalise  # noqa: E402

HF = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"
CACHE = Path(os.environ.get("FLIGHT_RIGHT_VOICE_CACHE",
                            Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlightRight/voice"))
REPORTS = ROOT / "ml_pipeline/reports"
SR = 16_000
MAX_SECONDS = 30.0

ATCOSIM_TEST = {"sm3", "zf3", "gm2"}
ATCOSIM_VAL = {"gm1", "gf1"}
ATCOSIM_TRAIN = {"sm1", "sm2", "sm4", "zf1", "zf2"}


def _files(repo: str) -> list[str]:
    found = sorted(glob.glob(str(HF / f"datasets--{repo.replace('/', '--')}/snapshots/*/data/*.parquet")))
    if not found:
        raise FileNotFoundError(f"{repo} is not in the Hugging Face cache; download it first.")
    return found


def _decode(blob: bytes) -> np.ndarray:
    audio, rate = sf.read(io.BytesIO(blob), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if rate != SR:
        audio = librosa.resample(audio, orig_sr=rate, target_sr=SR)
    return np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)


def _contaminated_ids() -> set[str]:
    reports = sorted(REPORTS.glob("voice_corpora_*.json"))
    for path in reversed(reports):
        ids = json.loads(path.read_text()).get("question_2_5", {}).get("contaminated_ids")
        if ids:
            return set(ids)
    raise FileNotFoundError("No voice_corpora report with contaminated_ids; run check_corpora.py.")


def _uwb_val(recording: str) -> bool:
    return int(hashlib.sha1(recording.encode()).hexdigest(), 16) % 10 == 0


def rows_atcosim_mirror():
    for path in _files("jlvdoorn/atco2-asr-atcosim"):
        table = pq.read_table(path, columns=["audio", "text"])
        audio = table.column("audio").combine_chunks()
        for blob, name, text in zip(audio.field("bytes").to_pylist(), audio.field("path").to_pylist(),
                                    table.column("text").to_pylist()):
            speaker = re.match(r"^([a-z]{2}\d)_", name or "")
            if speaker:
                spk = speaker.group(1)
                split = "test" if spk in ATCOSIM_TEST else "val" if spk in ATCOSIM_VAL else \
                    "train" if spk in ATCOSIM_TRAIN else None
                assert split, f"unplanned ATCOSIM speaker {spk}"
                yield dict(uid=f"atcosim/{name}", corpus="atcosim", group=spk, split=split,
                           role="ATCO", text_raw=text), blob
            else:
                recording = re.sub(r"\.wav$", "", name or "")
                yield dict(uid=f"atco2_mirror/{name}", corpus="atco2_mirror", group=recording[:40],
                           split="excluded", role="", text_raw=text,
                           reason="ATCO2 clips are never used for training (cross-corpus test)"), blob


def rows_uwb():
    by_split = {}
    for path in _files("Jzuluaga/uwb_atcc"):
        by_split.setdefault(Path(path).name.split("-")[0], []).append(path)
    recordings = {s: {i.split("_")[1] for p in ps for i in pq.read_table(p, columns=["id"]).column("id").to_pylist()}
                  for s, ps in by_split.items()}
    both = recordings["train"] & recordings["test"]
    for published, paths in by_split.items():
        for path in paths:
            table = pq.read_table(path, columns=["id", "audio", "text"])
            audio = table.column("audio").combine_chunks()
            for uid, blob, text in zip(table.column("id").to_pylist(), audio.field("bytes").to_pylist(),
                                       table.column("text").to_pylist()):
                recording, role = uid.split("_")[1], uid.rsplit("_", 1)[-1]
                if recording in both:
                    split, reason = "excluded", "recording appears in both published splits"
                elif published == "test":
                    split, reason = "test", None
                else:
                    split, reason = ("val" if _uwb_val(recording) else "train"), None
                yield dict(uid=f"uwb/{uid}", corpus="uwb", group=recording, split=split, role=role,
                           text_raw=text, reason=reason), blob


def rows_atco2_test(contaminated: set[str]):
    for path in _files("Jzuluaga/atco2_corpus_1h"):
        table = pq.read_table(path, columns=["id", "audio", "text"])
        audio = table.column("audio").combine_chunks()
        for uid, blob, text in zip(table.column("id").to_pylist(), audio.field("bytes").to_pylist(),
                                   table.column("text").to_pylist()):
            recording = re.sub(r"-[A-Z]__\d{6}-\d{6}$", "", uid.replace("atco2_test-set-1h_", ""))
            yield dict(uid=f"atco2/{uid}", corpus="atco2", group=recording, split="test",
                       role="", text_raw=text, contaminated=uid in contaminated), blob


def rows_svarah():
    """Svarah (AI4Bharat, CC BY 4.0): real Indian-accented English, TEST ONLY.

    Revised speech plan, step 6: "how it handles Indian voices -> on Svarah, real humans".
    Gated on Hugging Face (accept once, share contact details). Svarah is general read and
    spontaneous English, not ATC phraseology, so a model's score on it mixes accent with
    vocabulary; it is reported beside the untouched baseline for exactly that reason.
    Column names are found rather than assumed, because the gate hid them when this was written."""
    from huggingface_hub import snapshot_download
    root = Path(snapshot_download("ai4bharat/Svarah", repo_type="dataset", allow_patterns=["*.parquet", "*.md"]))
    for path in sorted(root.rglob("*.parquet")):
        table = pq.read_table(path)
        names = table.schema.names
        audio_col = next(n for n in names if str(table.schema.field(n).type).startswith("struct") and "bytes" in str(table.schema.field(n).type))
        text_col = next(n for n in ("text", "transcript", "transcription", "sentence", "normalized_text") if n in names)
        # Svarah carries no speaker id (checked 27 Sep 2026); the speaker's first language is the
        # grouping, so results can be broken down by it (Marathi is Mumbai's language).
        speaker_col = next((n for n in ("speaker_id", "speaker", "client_id", "primary_language") if n in names), None)
        audio = table.column(audio_col).combine_chunks()
        speakers = table.column(speaker_col).to_pylist() if speaker_col else [None] * len(table)
        for i, (blob, text, spk) in enumerate(zip(audio.field("bytes").to_pylist(),
                                                  table.column(text_col).to_pylist(), speakers)):
            yield dict(uid=f"svarah/{path.stem}/{i}", corpus="svarah", group=str(spk or path.stem),
                       split="test", role="", text_raw=text), blob


def append(source_name: str) -> None:
    """Add one more test corpus to an existing cache without re-decoding the others."""
    sources = {"svarah": rows_svarah}
    manifest_path, bin_path = CACHE / "manifest.parquet", CACHE / "audio_int16.bin"
    manifest = pd.read_parquet(manifest_path)
    manifest = manifest[manifest.corpus != source_name]
    offset, records = bin_path.stat().st_size // 2, []
    with open(bin_path, "ab") as out:
        for meta, blob in sources[source_name]():
            samples = _decode(blob)
            out.write(samples.tobytes())
            meta.update(offset=offset, n_samples=len(samples), duration_s=len(samples) / SR,
                        text=normalise(meta["text_raw"]), contaminated=False)
            if meta["duration_s"] > MAX_SECONDS or not meta["text"]:
                meta.update(split="excluded", reason="longer than 30 s or empty transcript")
            offset += len(samples)
            records.append(meta)
    pd.concat([manifest, pd.DataFrame(records)], ignore_index=True).to_parquet(manifest_path, index=False)
    added = pd.DataFrame(records)
    print(f"added {source_name}: {len(added)} clips, {added.duration_s.sum() / 3600:.2f} h, "
          f"{added.group.nunique()} speakers/groups")


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--add":
        append(sys.argv[2])
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    bin_path, manifest_path = CACHE / "audio_int16.bin", CACHE / "manifest.parquet"
    contaminated = _contaminated_ids()
    records, offset = [], 0
    with open(bin_path, "wb") as out:
        for source in (rows_atcosim_mirror(), rows_uwb(), rows_atco2_test(contaminated)):
            for meta, blob in source:
                samples = _decode(blob)
                out.write(samples.tobytes())
                meta.update(offset=offset, n_samples=len(samples),
                            duration_s=len(samples) / SR, text=normalise(meta["text_raw"]))
                offset += len(samples)
                if meta["split"] != "excluded":
                    if meta["duration_s"] > MAX_SECONDS:
                        meta.update(split="excluded", reason=f"longer than {MAX_SECONDS:.0f} s")
                    elif not meta["text"]:
                        meta.update(split="excluded", reason="empty transcript after normalising")
                records.append(meta)
                if len(records) % 2000 == 0:
                    print(f"  {len(records):,} clips decoded", flush=True)
    manifest = pd.DataFrame(records)
    manifest["contaminated"] = manifest.get("contaminated", False).fillna(False).astype(bool)
    manifest.to_parquet(manifest_path, index=False)

    # The split must be group-disjoint inside each corpus. Refuse to finish otherwise.
    for corpus, frame in manifest[manifest.split != "excluded"].groupby("corpus"):
        owners = frame.groupby("group")["split"].nunique()
        leaked = owners[owners > 1]
        assert leaked.empty, f"{corpus}: groups in more than one split: {list(leaked.index)[:5]}"

    summary = (manifest.groupby(["corpus", "split"])
               .agg(clips=("uid", "size"), hours=("duration_s", lambda s: round(s.sum() / 3600, 2)),
                    groups=("group", "nunique")).reset_index())
    report = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "cache": str(CACHE),
        "sample_rate": SR,
        "split_rule": {"atcosim_test": sorted(ATCOSIM_TEST), "atcosim_val": sorted(ATCOSIM_VAL),
                       "atcosim_train": sorted(ATCOSIM_TRAIN),
                       "uwb": "published test = test; train recordings with sha1 % 10 == 0 = val; "
                              "recordings in both published splits excluded",
                       "atco2_mirror": "excluded from training",
                       "atco2": "test only; contaminated flag from voice_corpora report"},
        "splits": summary.to_dict(orient="records"),
        "atco2_clean_clips": int(((manifest.corpus == "atco2") & ~manifest.contaminated
                                  & (manifest.split == "test")).sum()),
        "excluded_reasons": manifest[manifest.split == "excluded"]["reason"].value_counts().to_dict(),
        "group_disjoint": True,
    }
    REPORTS.mkdir(exist_ok=True)
    out_path = REPORTS / f"voice_cache_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(summary.to_string(index=False))
    print(f"clean ATCO2 clips: {report['atco2_clean_clips']}")
    print(f"wrote {manifest_path} ({offset * 2 / 1e9:.2f} GB audio) and {out_path}")


if __name__ == "__main__":
    main()
