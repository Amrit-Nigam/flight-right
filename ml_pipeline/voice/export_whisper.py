"""Turn a LoRA adapter into an ordinary Whisper checkpoint that any code path can load.

    python ml_pipeline/voice/export_whisper.py --adapter <run dir>/best_adapter --name flightright-whisper-small-atc-p1

Merges the adapter into the base weights (peft ``merge_and_unload``), saves model and processor
in Hugging Face format under <voice cache>/models/<name>, and converts that to CTranslate2 int8.
After this, our own model is named exactly like a published one -- by setting
FLIGHT_RIGHT_ASR_MODEL_ID to the directory -- and nothing else changes (plan 4.3 / 9.3).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ml_pipeline.voice.build_audio_cache import CACHE  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--base", default=None, help="defaults to the base recorded in the adapter config")
    ap.add_argument("--output-root", type=Path, default=CACHE / "models")
    ap.add_argument("--ct2-root", type=Path, default=None)
    args = ap.parse_args()
    from peft import PeftConfig, PeftModel
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    base = args.base or PeftConfig.from_pretrained(args.adapter).base_model_name_or_path
    model = WhisperForConditionalGeneration.from_pretrained(base)
    model = PeftModel.from_pretrained(model, args.adapter).merge_and_unload()
    model.generation_config.forced_decoder_ids = None
    out = args.output_root / args.name
    if out.exists():
        raise SystemExit(f"Refusing to overwrite existing export: {out}")
    model.save_pretrained(out)
    processor = WhisperProcessor.from_pretrained(base)
    processor.save_pretrained(out)
    # transformers 5 writes the audio settings as processor_config.json; faster-whisper and the
    # CTranslate2 converter look for preprocessor_config.json, so write that name too.
    processor.feature_extractor.save_pretrained(out)
    (out / "flightright_provenance.json").write_text(json.dumps(
        {"base_model": base, "adapter": str(Path(args.adapter).resolve()),
         "train_state": str(Path(args.adapter).resolve().parent / "state.json")}, indent=2))
    from ml_pipeline.voice import transcribe
    if args.ct2_root is not None:
        transcribe.CT2_DIR = args.ct2_root
    print("merged:", out)
    print("ctranslate2:", transcribe.ct2_path(str(out), "int8_float16"))


if __name__ == "__main__":
    main()
