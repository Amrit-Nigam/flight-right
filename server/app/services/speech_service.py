"""The speech chain, served: audio -> transcript -> clearance -> the aircraft it is for.

Plan Phases 4.3, 6 and 7.3, joined up. One call, `hear()`, runs the whole chain and records
every step:

1. transcribe with the model named by ASR_MODEL_ID (config.py; the only place a speech
   model is named) -> `transcriptions` row with model_id, quantisation and asr_version;
2. extract callsign | action | value with the rule-based extractor (ml_pipeline/voice/extract.py);
3. snap the heard callsign onto the aircraft visible RIGHT NOW (ml_pipeline/voice/callsigns.py,
   rapidfuzz over their spoken forms) -- post-processing, never a prompt to the recogniser;
4. hand the result to clearance_service.submit(), the single door every clearance comes
   through, which validates it, applies it if its confidence clears the floor, and writes
   `extracted_clearances` plus an audit row.

Nothing here decides what is applied: step 4 does, exactly as for a typed clearance.

If ASR_MODEL_ID is empty the service says so and does nothing else. The model is loaded on
first use, not at startup, so a dashboard that never hears a clip never pays for it.
"""
from __future__ import annotations

import io
import sys
import threading
import time
from typing import Any

import numpy as np

from ..config import ASR_MODEL_ID, ASR_QUANTISATION, PROJECT_ROOT
from .clearance_service import clearance_service
from .database import database

sys.path.insert(0, str(PROJECT_ROOT))
from ml_pipeline.voice.callsigns import match  # noqa: E402
from ml_pipeline.voice.extract import asr_confidence_from_logprob, extract  # noqa: E402

SR = 16_000


def decode_wav(payload: bytes) -> np.ndarray:
    """Any soundfile-readable audio -> 16 kHz mono float32."""
    import soundfile as sf
    audio, rate = sf.read(io.BytesIO(payload), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if rate != SR:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(int(rate), SR)
        audio = resample_poly(audio, SR // g, int(rate) // g).astype(np.float32)
    return audio


class SpeechService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model = None
        self._error: str | None = None

    def status(self) -> dict[str, Any]:
        from ml_pipeline.voice.transcribe import ASR_VERSION
        return {"modelId": ASR_MODEL_ID or None, "quantisation": ASR_QUANTISATION if ASR_MODEL_ID else None,
                "asrVersion": ASR_VERSION, "loaded": self._model is not None, "error": self._error,
                "installed": bool(ASR_MODEL_ID)}

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from ml_pipeline.voice.transcribe import load_model
                    try:
                        self._model = load_model(ASR_MODEL_ID, ASR_QUANTISATION)
                        self._error = None
                    except Exception as failure:                     # noqa: BLE001
                        self._error = f"{type(failure).__name__}: {failure}"[:500]
                        raise
        return self._model

    def hear(self, audio: np.ndarray, clip_ref: str, flights: list[dict],
             transcript: str | None = None, heard_at: float | None = None) -> dict[str, Any]:
        """Run the chain on one transmission. ``transcript`` skips recognition (cached rows)."""
        from ml_pipeline.voice.transcribe import ASR_VERSION, transcribe_array
        if not ASR_MODEL_ID and transcript is None:
            reason = "no speech model installed (set FLIGHT_RIGHT_ASR_MODEL_ID)"
            return {"ok": False, "reason": reason, "error": reason}
        started = time.time()
        logprob = None
        if transcript is None:
            result = transcribe_array(self._load(), audio)
            transcript, logprob = result["hyp"], result["avg_logprob"]
        asr_confidence = asr_confidence_from_logprob(logprob)
        transcription_id = database.record_transcription({
            "clip_ref": clip_ref, "heard_at": heard_at, "transcript": transcript,
            "model_id": ASR_MODEL_ID or "cached", "quantisation": ASR_QUANTISATION,
            "asr_version": ASR_VERSION, "confidence": asr_confidence})
        extracted = extract(transcript, asr_confidence)
        visible = [str(f.get("callsign") or "").strip() for f in flights if f.get("callsign")]
        snapped = match(extracted.text, visible) if visible else {"code": None, "score": 0.0, "margin": 0.0}
        out: dict[str, Any] = {
            "ok": True, "transcriptionId": transcription_id, "transcript": transcript,
            "asrConfidence": asr_confidence, "extracted": extracted.to_dict(),
            "callsignMatch": {**snapped, "heard": extracted.callsign_spoken, "listSize": len(visible)},
            "clearance": None, "seconds": round(time.time() - started, 3),
            "modelId": ASR_MODEL_ID or "cached", "quantisation": ASR_QUANTISATION,
        }
        if extracted.action and snapped["code"]:
            confidence = extracted.confidence * (snapped["score"] / 100.0)
            out["clearance"] = clearance_service.submit(
                {"callsign": snapped["code"], "action": extracted.action, "value": extracted.value,
                 "fix": extracted.fix, "confidence": round(confidence, 3), "transcription_id": transcription_id},
                flights, source=f"asr:{ASR_MODEL_ID or 'cached'}")
        elif extracted.action:
            out["reason"] = "a clearance was heard but no visible aircraft matched the callsign"
        else:
            out["reason"] = "no clearance the trajectory model can use was heard"
        return out


speech_service = SpeechService()
