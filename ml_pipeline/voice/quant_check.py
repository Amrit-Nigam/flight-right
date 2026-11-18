"""Plan 4.2: does int8 quantisation cost accuracy? Measured, not assumed.

    python ml_pipeline/voice/quant_check.py --model jlvdoorn/whisper-large-v3-atco2-asr-atcosim

Runs the same 50 clean ATCO2 clips through (a) the plain transformers model in fp16 and
(b) the CTranslate2 int8 conversion served by faster-whisper, both with beam 5 and no
timestamps, and compares word error rate. The plan's rule: if int8 costs more than about one
point, serve fp16 and accept the slower run; either way, record which was used (it is part of
every transcription row's model version).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ml_pipeline.voice.build_audio_cache import CACHE, SR  # noqa: E402
from ml_pipeline.voice.evaluate_voice import wer  # noqa: E402
from ml_pipeline.voice.text_norm import normalise  # noqa: E402
from ml_pipeline.voice.transcribe import load_model, transcribe_array  # noqa: E402

N_CLIPS = 50


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    args = ap.parse_args()
    manifest = pd.read_parquet(CACHE / "manifest.parquet")
    clips = manifest[(manifest.corpus == "atco2") & ~manifest.contaminated & (manifest.split == "test")]
    clips = clips.sample(N_CLIPS, random_state=42)
    data = np.memmap(CACHE / "audio_int16.bin", dtype=np.int16, mode="r")
    audio = [data[int(r.offset): int(r.offset) + int(r.n_samples)].astype(np.float32) / 32768.0
             for r in clips.itertuples()]

    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    processor = WhisperProcessor.from_pretrained(args.model)
    model = WhisperForConditionalGeneration.from_pretrained(args.model, dtype=torch.float16).cuda().eval()
    t0, fp16 = time.time(), []
    for a in audio:
        feats = processor.feature_extractor(a, sampling_rate=SR, return_tensors="pt").input_features.cuda().half()
        with torch.no_grad():
            ids = model.generate(input_features=feats, language="en", task="transcribe", num_beams=5, max_new_tokens=160)
        fp16.append(processor.tokenizer.batch_decode(ids, skip_special_tokens=True)[0])
    fp16_seconds = time.time() - t0
    del model
    torch.cuda.empty_cache()

    ct2 = load_model(args.model, "int8_float16")
    t0 = time.time()
    int8 = [transcribe_array(ct2, a)["hyp"] for a in audio]
    int8_seconds = time.time() - t0

    refs = list(clips.text)
    report = {"measured_at_utc": datetime.now(timezone.utc).isoformat(), "model": args.model, "clips": N_CLIPS,
              "corpus": "ATCO2 clean test clips (random 50, seed 42)",
              "wer_transformers_fp16": wer(refs, [normalise(h) for h in fp16]),
              "wer_ctranslate2_int8": wer(refs, [normalise(h) for h in int8]),
              "seconds_fp16": round(fp16_seconds, 1), "seconds_int8": round(int8_seconds, 1),
              "identical_transcripts": int(sum(normalise(a) == normalise(b) for a, b in zip(fp16, int8)))}
    report["int8_cost_points"] = round(report["wer_ctranslate2_int8"] - report["wer_transformers_fp16"], 2)
    report["decision"] = "serve int8" if report["int8_cost_points"] <= 1.0 else "serve fp16 (int8 costs more than one point)"
    out = ROOT / "ml_pipeline/reports" / f"voice_quant_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
