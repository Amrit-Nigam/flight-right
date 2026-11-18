"""Make clean speech sound like a VHF radio channel (revised speech plan, step 4).

Pure numpy/scipy, so both the training environment and the separate text-to-speech
environment (venv_tts, which pins an old transformers) can import it.

    python ml_pipeline/voice/radio_channel.py      # build the noise bank from UWB-ATCC train

What the channel does, in order, and why:
1. Band-limit to 300-3,400 Hz (4th-order Butterworth, zero phase). Aeronautical VHF voice
   is AM with an audio passband of about 300-3,400 Hz -- the same as a telephone channel --
   so studio-quality high and low frequencies must not survive.
2. Down to 8 kHz and back to 16 kHz, so no energy is left above 4 kHz (UWB-ATCC itself is
   distributed at 8 kHz; card: "8kHz, 16bit PCM, mono").
3. Mild compression (tanh soft clip, gain 2-5). Radios run automatic gain control and the
   recordings are visibly level-compressed; the gain range is our own choice, not measured.
4. Real background noise at a random signal-to-noise ratio of 5-20 dB. The noise is cut
   from UWB-ATCC TRAINING recordings (never test): the quietest 10 % of 20 ms frames of
   each clip, i.e. the channel's own hiss and hum between words. Using real channel noise
   rather than synthetic white noise is the point of the step.

LICENCE, stated because it propagates: UWB-ATCC is CC BY-NC-SA 4.0, so any audio mixed with
this noise bank, and any model trained on that audio, is non-commercial.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt

SR = 16_000
BAND = (300.0, 3400.0)
SNR_DB = (5.0, 20.0)
_SOS = butter(4, BAND, btype="bandpass", fs=SR, output="sos")


def radio(audio: np.ndarray, noise_bank: np.ndarray | None, rng: np.random.Generator) -> np.ndarray:
    """16 kHz float audio in, 16 kHz float audio out, sounding like a radio channel."""
    x = sosfiltfilt(_SOS, audio.astype(np.float64))
    x = resample_poly(resample_poly(x, 1, 2), 2, 1)[: len(audio)]
    peak = np.max(np.abs(x)) or 1.0
    gain = rng.uniform(2.0, 5.0)
    x = np.tanh(gain * x / peak) / np.tanh(gain)
    if noise_bank is not None and len(noise_bank) > len(x):
        start = rng.integers(0, len(noise_bank) - len(x))
        noise = noise_bank[start: start + len(x)].astype(np.float64)
        speech_power = np.mean(x ** 2) or 1e-9
        noise_power = np.mean(noise ** 2) or 1e-9
        snr = rng.uniform(*SNR_DB)
        x = x + noise * np.sqrt(speech_power / (noise_power * 10 ** (snr / 10)))
    return (0.9 * x / (np.max(np.abs(x)) or 1.0)).astype(np.float32)


def build_noise_bank(max_minutes: float = 10.0) -> Path:
    """The quietest 10 % of 20 ms frames of UWB-ATCC TRAIN clips, concatenated."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import pandas as pd
    from ml_pipeline.voice.build_audio_cache import CACHE
    manifest = pd.read_parquet(CACHE / "manifest.parquet")
    rows = manifest[(manifest.corpus == "uwb") & (manifest.split == "train")].sample(frac=1.0, random_state=42)
    data = np.memmap(CACHE / "audio_int16.bin", dtype=np.int16, mode="r")
    frame, pieces, total, limit = 320, [], 0, int(max_minutes * 60 * SR)
    for row in rows.itertuples():
        clip = data[int(row.offset): int(row.offset) + int(row.n_samples)].astype(np.float32)
        frames = clip[: len(clip) // frame * frame].reshape(-1, frame)
        if len(frames) < 20:
            continue
        energy = (frames ** 2).mean(axis=1)
        quiet = frames[energy <= np.quantile(energy, 0.10)]
        pieces.append(quiet.reshape(-1))
        total += quiet.size
        if total >= limit:
            break
    bank = np.concatenate(pieces)[:limit].astype(np.int16)
    out = CACHE / "tts" / "uwb_noise_bank_int16.npy"
    out.parent.mkdir(parents=True, exist_ok=True)
    np.save(out, bank)
    print(f"noise bank: {len(bank) / SR / 60:.1f} min from UWB-ATCC train -> {out}")
    return out


if __name__ == "__main__":
    build_noise_bank()
