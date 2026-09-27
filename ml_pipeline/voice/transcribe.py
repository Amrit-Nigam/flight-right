"""Speech to text, one code path for every model (plan 4.1-4.4).

    python ml_pipeline/voice/transcribe.py --model jlvdoorn/whisper-medium-atcosim --split test

A model is named by its Hugging Face id, or by a local directory holding a Hugging Face
Whisper checkpoint (our own fine-tune, merged). Either way it is converted ONCE to
CTranslate2 and served by faster-whisper, which is what fits Whisper large into 6 GB
(plan 4.2: int8 = 2,926 MB). Nothing else in the project names a model: the backend reads
ASR_MODEL_ID and ASR_QUANTISATION from server/app/config.py and calls load_model().

Transcripts are cached per (model, quantisation) under the voice cache, so each model is run
over each clip once and every later measurement reads the cache. Every row carries the
model id, the quantisation and the decoding settings (plan 4.3: model version on every row).

Decoding settings are fixed and identical for every model: English, transcribe, beam 5, no
timestamps, no conditioning on previous text, no voice-activity filter (the clips are
already segmented). Changing one would make the comparison unfair, so they are constants.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ml_pipeline.voice.build_audio_cache import CACHE, SR  # noqa: E402

CT2_DIR = CACHE / "ct2"
TRANSCRIPTS = CACHE / "transcripts"
DECODING = dict(language="en", task="transcribe", beam_size=5, without_timestamps=True,
                condition_on_previous_text=False, vad_filter=False, temperature=0.0)
ASR_VERSION = "fw1-beam5-v1"   # bump if DECODING changes, so cached rows cannot be mixed


def _slug(model_id: str) -> str:
    """A filesystem-safe name for a model id or a local model directory."""
    path = Path(model_id)
    if path.exists():
        return "local__" + path.resolve().name
    return model_id.replace("/", "__")


def ct2_path(model_id: str, quantisation: str) -> Path:
    """Convert a Hugging Face Whisper checkpoint to CTranslate2, once."""
    out = CT2_DIR / f"{_slug(model_id)}__{quantisation}"
    if (out / "model.bin").exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    converter = Path(sys.executable).with_name("ct2-transformers-converter")
    wanted = ["tokenizer.json", "preprocessor_config.json"]
    if Path(model_id).exists():   # a local checkpoint: copy only what is actually there
        wanted = [f for f in wanted if (Path(model_id) / f).exists()]
    command = [str(converter), "--model", model_id, "--output_dir", str(out),
               "--quantization", quantisation, "--copy_files", *wanted]
    print("converting:", " ".join(command), flush=True)
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        # Some checkpoints ship tokenizer files under other names; retry without copying.
        command = command[: command.index("--copy_files")]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise RuntimeError(f"conversion failed for {model_id}: {result.stderr[-2000:]}")
    missing = [f for f in ("tokenizer.json", "preprocessor_config.json") if not (out / f).exists()]
    if missing:
        # Without these faster-whisper silently falls back to a stock tokenizer and 80 mel bins.
        raise RuntimeError(f"converted {model_id} but {missing} were not copied into {out}")
    return out


def _cuda_libraries_on_path() -> None:
    """CTranslate2 needs cuBLAS 12 and cuDNN 9 at run time and looks for them on the DLL path.

    PyTorch's CUDA 12 wheel already ships both (torch/lib/cublas64_12.dll, cudnn64_9.dll), so
    point Windows at that folder instead of installing a second copy. Measured 26 Sep: without
    this, the first GPU transcription fails with "cublas64_12.dll is not found"."""
    if sys.platform != "win32":
        return
    import torch
    lib = Path(torch.__file__).parent / "lib"
    if lib.exists() and str(lib) not in os.environ.get("PATH", ""):
        os.add_dll_directory(str(lib))
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")


def load_model(model_id: str, quantisation: str = "int8_float16", device: str = "auto"):
    from faster_whisper import WhisperModel
    path = ct2_path(model_id, quantisation)
    if device == "auto":
        import ctranslate2
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    if device == "cuda":
        _cuda_libraries_on_path()
    compute = quantisation if device == "cuda" else quantisation.replace("_float16", "")
    return WhisperModel(str(path), device=device, compute_type=compute)


def transcribe_array(model, audio: np.ndarray) -> dict:
    """One clip -> text plus the recogniser's own confidence (mean token log-probability)."""
    segments, _ = model.transcribe(audio.astype(np.float32), **DECODING)
    segments = list(segments)
    text = " ".join(s.text.strip() for s in segments).strip()
    logprob = float(np.mean([s.avg_logprob for s in segments])) if segments else float("nan")
    return {"hyp": text, "avg_logprob": logprob}


def transcribe_rows(model_id: str, rows: pd.DataFrame, quantisation: str = "int8_float16",
                    device: str = "auto") -> pd.DataFrame:
    """Transcribe manifest rows, reusing every clip already in this model's cache."""
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    cache_path = TRANSCRIPTS / f"{_slug(model_id)}__{quantisation}.parquet"
    done = pd.read_parquet(cache_path) if cache_path.exists() else pd.DataFrame(columns=["uid"])
    if "asr_version" in done:
        done = done[done.asr_version == ASR_VERSION]
    todo = rows[~rows.uid.isin(set(done.uid))]
    if len(todo):
        model = load_model(model_id, quantisation, device)
        data = np.memmap(CACHE / "audio_int16.bin", dtype=np.int16, mode="r")
        out, started = [], time.time()
        for n, row in enumerate(todo.itertuples(), 1):
            audio = data[int(row.offset): int(row.offset) + int(row.n_samples)].astype(np.float32) / 32768.0
            t0 = time.time()
            result = transcribe_array(model, audio)
            out.append({"uid": row.uid, **result, "seconds": time.time() - t0,
                        "audio_seconds": row.n_samples / SR, "model_id": model_id,
                        "quantisation": quantisation, "asr_version": ASR_VERSION})
            if n % 100 == 0:
                print(f"  {model_id}: {n}/{len(todo)} clips, {time.time() - started:.0f} s", flush=True)
                pd.concat([done, pd.DataFrame(out)]).to_parquet(cache_path, index=False)
        done = pd.concat([done, pd.DataFrame(out)], ignore_index=True)
        done.to_parquet(cache_path, index=False)
    return rows[["uid"]].merge(done, on="uid", how="left")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--quantisation", default="int8_float16")
    p.add_argument("--device", default="auto")
    p.add_argument("--corpus", default="atco2,atcosim,uwb")
    p.add_argument("--split", default="test")
    args = p.parse_args()
    manifest = pd.read_parquet(CACHE / "manifest.parquet")
    rows = manifest[(manifest.split == args.split) & manifest.corpus.isin(args.corpus.split(","))]
    result = transcribe_rows(args.model, rows, args.quantisation, args.device)
    print(f"{len(result)} clips; real-time factor "
          f"{result.seconds.sum() / max(result.audio_seconds.sum(), 1e-9):.3f}")


if __name__ == "__main__":
    main()
