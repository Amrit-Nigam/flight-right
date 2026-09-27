"""The radio panel's demo clips (plan 7.3), and their pre-computed transcripts.

Three steps, two environments:

    python ml_pipeline/voice/demo_clips.py --recorded                  # real ATCO2 radio, main venv
    <venv_tts>/Scripts/python ml_pipeline/voice/demo_clips.py --synthetic   # needs Indic Parler-TTS
    python ml_pipeline/voice/demo_clips.py --transcribe <model id>     # main venv, GPU

Output: <voice cache>/demo_clips/<id>.wav and index.json, which the backend serves.

WHAT EACH CLIP IS, and it is said on screen:
- RECORDED: real controller radio from the ATCO2 test set (European airports). Its callsign
  is not in the Mumbai sky, so the chain correctly reports "no visible aircraft matched".
  That is the honest demonstration of the matching step refusing a wrong answer.
- SYNTHETIC VOICE: Indic Parler-TTS reading an instruction to the real aircraft in the
  demo encounter (IGO086 x FDB1346, the pair the replay opens on). The level and heading are
  derived from what those aircraft were doing at that moment in the recording. Demo only:
  generated audio is never scored (plan rule 7).

Pre-transcribing means the demo runs zero recognition live (plan 7.3: "zero inference at demo
time means zero demo risk"); the panel's TRANSCRIBE NOW button runs it live on request.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline" / "voice"))
CACHE = Path(os.environ.get("FLIGHT_RIGHT_VOICE_CACHE",
                            Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlightRight/voice"))
OUT = Path(os.environ.get("FLIGHT_RIGHT_SPEECH_DEMO_DIR", CACHE / "demo_clips"))
SR = 16_000
DEMO_SESSION = "session_c_20260904_204503_combined"
DIGITS = "zero one two three four five six seven eight nine".split()


def _index() -> list[dict]:
    path = OUT / "index.json"
    return json.loads(path.read_text(encoding="utf8")) if path.exists() else []


def _save(index: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.json").write_text(json.dumps(index, indent=2), encoding="utf8")


def _upsert(entry: dict) -> None:
    index = [e for e in _index() if e["id"] != entry["id"]] + [entry]
    _save(sorted(index, key=lambda e: e["id"]))


def recorded() -> None:
    """Two real ATCO2 clean-set clips that carry a level clearance."""
    import soundfile as sf
    from ml_pipeline.voice.evaluate_voice import gold_atco2
    gold = gold_atco2()
    picks = gold[(~gold.contaminated) & gold.gold_action.isin(["DESCEND", "CLIMB"]) & gold.truth_code.notna()].head(2)
    data = np.memmap(CACHE / "audio_int16.bin", dtype=np.int16, mode="r")
    for n, row in enumerate(picks.itertuples(), 1):
        clip_id = f"recorded_atco2_{n}"
        audio = data[int(row.offset): int(row.offset) + int(row.n_samples)]
        OUT.mkdir(parents=True, exist_ok=True)
        sf.write(OUT / f"{clip_id}.wav", audio, SR, subtype="PCM_16")
        _upsert({"id": clip_id, "synthetic": False, "label": f"{row.truth_code} — {row.gold_action.lower()}",
                 "source": f"Real controller radio, ATCO2 test set ({row.recording.split('_')[0]}); "
                           "not a Mumbai aircraft, so no visible aircraft should match.",
                 "truth": {"callsign": row.truth_code, "action": row.gold_action, "value": row.gold_value},
                 "transcripts": {}})
        print("wrote", clip_id, row.text_raw)


def _encounter_state() -> dict[str, dict]:
    raw = pd.read_parquet(ROOT / f"ml_pipeline/data/raw/{DEMO_SESSION}.parquet",
                          columns=["callsign", "baro_altitude", "true_track", "fetch_timestamp_utc"])
    raw["callsign"] = raw.callsign.fillna("").str.strip()
    out = {}
    for code in ("IGO086", "FDB1346"):
        rows = raw[raw.callsign == code].sort_values("fetch_timestamp_utc")
        mid = rows.iloc[len(rows) // 2]
        out[code] = {"alt_ft": float(mid.baro_altitude) * 3.28084, "track": float(mid.true_track)}
    return out


def synthetic() -> None:
    """Indian-accented synthetic speech of instructions to the demo pair (venv_tts)."""
    import random

    import soundfile as sf
    from radio_channel import radio
    from synthesize import Synth, description, english_speakers
    state = _encounter_state()
    igo_level = int(state["IGO086"]["alt_ft"] // 1000 * 10 - 20)            # 2,000 ft below, as a flight level
    fdb_heading = int(round(((state["FDB1346"]["track"] + 30) % 360) / 5) * 5) or 360
    lvl = " ".join(DIGITS[int(c)] for c in f"{igo_level:03d}")
    hdg = " ".join(DIGITS[int(c)] for c in f"{fdb_heading:03d}")
    scripts = [
        ("synthetic_igo086_descend", f"ifly zero eight six descend flight level {lvl}",
         "IGO086", "DESCEND", igo_level * 100.0),
        ("synthetic_igo086_readback", f"descending flight level {lvl} ifly zero eight six",
         "IGO086", "DESCEND", igo_level * 100.0),
        ("synthetic_fdb1346_turn", f"sky dubai one three four six turn right heading {hdg}",
         "FDB1346", "TURN", float(fdb_heading)),
    ]
    synth, rng = Synth("cuda"), random.Random(7)
    speakers = english_speakers()
    bank = np.load(CACHE / "tts" / "uwb_noise_bank_int16.npy").astype(np.float32) / 32768.0
    for clip_id, text, code, action, value in scripts:
        speaker = rng.choice(speakers)
        clean = synth([text.replace("ifly", "eye fly")], [description(speaker, rng)])[0]
        audio = radio(clean, bank, np.random.default_rng(7))
        OUT.mkdir(parents=True, exist_ok=True)
        sf.write(OUT / f"{clip_id}.wav", (audio * 32767).astype(np.int16), SR, subtype="PCM_16")
        _upsert({"id": clip_id, "synthetic": True, "label": f"{code} — {text}",
                 "source": f"Synthetic Indian-accented voice (Indic Parler-TTS, speaker {speaker}, AI4Bharat) "
                           "through a simulated radio channel. Real callsign from the replayed recording; "
                           "demo only, never used in a reported number.",
                 "truth": {"callsign": code, "action": action, "value": value}, "transcripts": {}})
        print("wrote", clip_id, text)


def transcribe(model_id: str) -> None:
    """Pre-compute each clip's transcript with one model, keyed by model id (main venv)."""
    import soundfile as sf
    from ml_pipeline.voice.transcribe import load_model, transcribe_array
    model = load_model(model_id)
    index = _index()
    for entry in index:
        audio, rate = sf.read(OUT / f"{entry['id']}.wav", dtype="float32")
        assert rate == SR
        entry.setdefault("transcripts", {})[model_id] = transcribe_array(model, audio)["hyp"]
        print(entry["id"], "->", entry["transcripts"][model_id])
    _save(index)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--recorded", action="store_true")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--transcribe")
    args = ap.parse_args()
    if args.recorded:
        recorded()
    if args.synthetic:
        synthetic()
    if args.transcribe:
        transcribe(args.transcribe)
