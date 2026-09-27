"""Speak the Mumbai scripts in Indian-accented English, then pass them through a radio channel.

Runs in its OWN environment, because parler-tts pins transformers==4.46.1 and the training
environment runs 5.x:

    %LOCALAPPDATA%/FlightRight/venv_tts/Scripts/python ml_pipeline/voice/synthesize.py --listen 20
    %LOCALAPPDATA%/FlightRight/venv_tts/Scripts/python ml_pipeline/voice/synthesize.py

Revised speech plan, step 3. Model: ai4bharat/indic-parler-tts (Apache 2.0; gated on
Hugging Face -- accept its terms once). No real person's voice is copied: the model's own
named speakers are selected by name in a text description, which is how the model card says
to use it. Credit AI4Bharat.

THE ENGLISH SPEAKER LIST IS READ FROM THE MODEL CARD at run time, not typed here, so it cannot
drift from what the model actually supports. Three of those speakers are held out: they speak
only validation rows, so the accent pass is validated on voices it never trained on. The
validation rows are also different AIRCRAFT (mumbai_scripts.py splits by icao24).

NEVER A TEST SET. Generated audio trains the accent pass and nothing else. Every reported
speech number comes from real recordings (ATCO2, ATCOSIM, UWB-ATCC, Svarah).

``--listen N`` writes N clips (clean and radio versions side by side) as WAV files for the
fifteen-minute listening check the plan asks a person to do before ten hours are generated:
if the voices sound wrong, everything downstream is wasted.
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml_pipeline" / "voice"))
from radio_channel import radio  # noqa: E402  (numpy/scipy only; safe in venv_tts)

CACHE = Path(os.environ.get("FLIGHT_RIGHT_VOICE_CACHE",
                            Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlightRight/voice"))
TTS = CACHE / "tts"
MODEL = "ai4bharat/indic-parler-tts"
SR = 16_000
HELD_OUT_SPEAKERS = 3
PACE = ["at a moderate pace", "slightly fast", "quite fast, like a busy air traffic controller"]
SEED = 42


def english_speakers() -> list[str]:
    """The English row of the model card's speaker table."""
    from huggingface_hub import hf_hub_download
    card = Path(hf_hub_download(MODEL, "README.md")).read_text(encoding="utf8")
    for line in card.splitlines():
        if re.match(r"\|\s*English\s*\|", line):
            names = line.split("|")[2]
            return [n.strip() for n in names.split(",") if n.strip()]
    raise RuntimeError("could not find the English speaker row in the model card")


def description(speaker: str, rng: random.Random) -> str:
    return (f"{speaker} speaks {rng.choice(PACE)} with a clear Indian English accent. "
            f"The recording is very close with almost no background noise.")


class Synth:
    def __init__(self, device: str):
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer
        self.torch, self.device = torch, device
        self.model = ParlerTTSForConditionalGeneration.from_pretrained(MODEL).to(device)
        self.tok = AutoTokenizer.from_pretrained(MODEL)
        self.desc_tok = AutoTokenizer.from_pretrained(self.model.config.text_encoder._name_or_path)
        self.rate = self.model.config.sampling_rate

    def __call__(self, texts: list[str], descriptions: list[str]) -> list[np.ndarray]:
        d = self.desc_tok(descriptions, return_tensors="pt", padding=True).to(self.device)
        p = self.tok(texts, return_tensors="pt", padding=True).to(self.device)
        with self.torch.no_grad():
            out = self.model.generate(input_ids=d.input_ids, attention_mask=d.attention_mask,
                                      prompt_input_ids=p.input_ids, prompt_attention_mask=p.attention_mask,
                                      return_dict_in_generate=True, do_sample=True)
        audios = []
        for i in range(len(texts)):
            length = int(out.audios_length[i]) if getattr(out, "audios_length", None) is not None else None
            wave = out.sequences[i, :length].float().cpu().numpy()
            audios.append(resample_poly(wave, SR, self.rate).astype(np.float32))
        return audios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=0, help="write N sample WAVs for a person to check, then stop")
    ap.add_argument("--limit", type=int, default=0, help="speak at most this many scripts")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()
    rng, nrng = random.Random(SEED), np.random.default_rng(SEED)
    scripts = pd.read_parquet(TTS / "mumbai_scripts.parquet")
    speakers = english_speakers()
    held_out = speakers[-HELD_OUT_SPEAKERS:]
    trainers = speakers[:-HELD_OUT_SPEAKERS]
    bank_path = TTS / "uwb_noise_bank_int16.npy"
    bank = np.load(bank_path).astype(np.float32) / 32768.0 if bank_path.exists() else None
    synth = Synth(args.device)
    print(f"{len(speakers)} English speakers on the model card; held out for validation: {held_out}")

    if args.listen:
        out = TTS / "listen"
        out.mkdir(parents=True, exist_ok=True)
        sample = scripts.sample(args.listen, random_state=SEED)
        for row, speaker in zip(sample.itertuples(), [rng.choice(speakers) for _ in range(len(sample))]):
            clean = synth([row.tts_text], [description(speaker, rng)])[0]
            sf.write(out / f"{row.script_id}_{speaker}_clean.wav", clean, SR)
            sf.write(out / f"{row.script_id}_{speaker}_radio.wav", radio(clean, bank, nrng), SR)
            print(f"  {row.script_id} {speaker}: {row.tts_text}")
        pd.DataFrame({"file": [p.name for p in sorted(out.glob("*.wav"))]}).to_csv(out / "index.csv", index=False)
        print(f"wrote {args.listen * 2} WAVs to {out} -- listen before generating the full set")
        return

    manifest_path, bin_path = TTS / "manifest.parquet", TTS / "audio_int16.bin"
    done = pd.read_parquet(manifest_path) if manifest_path.exists() else pd.DataFrame(columns=["script_id"])
    todo = scripts[~scripts.script_id.isin(set(done.script_id))]
    if args.limit:
        todo = todo.head(max(0, args.limit - len(done)))
    offset = bin_path.stat().st_size // 2 if bin_path.exists() else 0
    rows, started = [], time.time()
    with open(bin_path, "ab") as sink:
        for start in range(0, len(todo), args.batch):
            chunk = todo.iloc[start: start + args.batch]
            voices = [rng.choice(held_out if s == "val" else trainers) for s in chunk.split]
            audios = synth(list(chunk.tts_text), [description(v, rng) for v in voices])
            for row, voice, clean in zip(chunk.itertuples(), voices, audios):
                if len(clean) < SR // 2 or len(clean) > 30 * SR:
                    continue                     # a failed or runaway generation; never kept
                pcm = np.clip(radio(clean, bank, nrng) * 32767, -32768, 32767).astype(np.int16)
                sink.write(pcm.tobytes())
                rows.append({"uid": f"tts/{row.script_id}", "script_id": row.script_id, "corpus": "tts_indian",
                             "group": row.icao24, "split": row.split, "role": row.role, "speaker": voice,
                             "text_raw": row.text, "text": row.text, "offset": offset, "n_samples": len(pcm),
                             "duration_s": len(pcm) / SR, "bin": "tts/audio_int16.bin", "contaminated": False})
                offset += len(pcm)
            if len(rows) >= 200 or start + args.batch >= len(todo):
                done = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
                done.to_parquet(manifest_path, index=False)
                rows = []
                rate = (time.time() - started) / max(1, start + len(chunk))
                print(f"  {len(done)}/{len(scripts)} spoken, {rate:.2f} s per clip", flush=True)
    print(f"done: {len(done)} clips in {manifest_path}")


if __name__ == "__main__":
    main()
