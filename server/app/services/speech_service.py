"""Passive radio: audio -> transcript -> speaker hint -> extracted aircraft intent.

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
from collections import deque
import logging
import re
import sys
import threading
import time
from typing import Any

import numpy as np

from ..config import ASR_DEVICE, ASR_MODEL_ID, ASR_QUANTISATION, PROJECT_ROOT
from .clearance_service import GROUP, clearance_service
from .database import database

sys.path.insert(0, str(PROJECT_ROOT))
from ml_pipeline.voice.callsigns import match  # noqa: E402
from ml_pipeline.voice.extract import asr_confidence_from_logprob, extract  # noqa: E402
from ml_pipeline.voice.radio_roles import infer_role  # noqa: E402

SR = 16_000
log = logging.getLogger("flightright.speech")


def decode_wav(payload: bytes) -> np.ndarray:
    """Any soundfile-readable audio -> 16 kHz mono float32."""
    import soundfile as sf
    with sf.SoundFile(io.BytesIO(payload)) as clip:
        if not 0 < clip.frames <= clip.samplerate * 30 or clip.channels > 8:
            raise ValueError("send a nonempty transmission of at most 30 seconds and eight channels")
        rate = clip.samplerate
        audio = clip.read(dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if not np.isfinite(audio).all():
        raise ValueError("audio contains nonfinite samples")
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
        self._inference_lock = threading.Lock()
        self._error: str | None = None
        self._conversation_lock = threading.RLock()
        self._messages = deque(maxlen=100)
        self._readbacks: dict[str, dict] = {}

    @staticmethod
    def device() -> str:
        """Where recognition runs: the same choice transcribe.load_model makes."""
        if ASR_DEVICE in ("cpu", "cuda"):
            return ASR_DEVICE
        try:
            import ctranslate2
            return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:                                            # noqa: BLE001
            return "cpu"

    def status(self) -> dict[str, Any]:
        from ml_pipeline.voice.transcribe import ASR_VERSION
        device = self.device()
        return {"modelId": ASR_MODEL_ID or None, "quantisation": ASR_QUANTISATION if ASR_MODEL_ID else None,
                "asrVersion": ASR_VERSION, "loaded": self._model is not None, "error": self._error,
                "installed": bool(ASR_MODEL_ID), "device": device}

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from ml_pipeline.voice.transcribe import load_model
                    try:
                        self._model = load_model(ASR_MODEL_ID, ASR_QUANTISATION, self.device())
                        self._error = None
                    except Exception as failure:                     # noqa: BLE001
                        self._error = f"{type(failure).__name__}: {failure}"[:500]
                        raise
        return self._model

    def warm_up(self) -> None:
        """Load the model and run it once on silence, so the first live transcription in a demo takes
        seconds, not ~16 s (measured 28 Sep on CPU: 6 s to load, 10 s for the first clip, then 2-4 s)."""
        if not ASR_MODEL_ID:
            return
        from ml_pipeline.voice.transcribe import transcribe_array
        try:
            started = time.time()
            with self._inference_lock:
                transcribe_array(self._load(), np.zeros(SR, dtype=np.float32))
            log.info("Speech model ready on %s in %.1f s: %s", self.device(), time.time() - started, ASR_MODEL_ID)
        except Exception as failure:                                     # noqa: BLE001
            log.warning("Speech model warm-up failed: %s", self._error or failure)

    def hear(self, audio: np.ndarray, clip_ref: str, flights: list[dict],
             transcript: str | None = None, heard_at: float | None = None,
             role: str = "auto", allow_apply: bool = True) -> dict[str, Any]:
        """Run the chain on one transmission. ``transcript`` skips recognition (cached rows)."""
        from ml_pipeline.voice.transcribe import transcribe_array
        if not ASR_MODEL_ID and transcript is None:
            reason = "no speech model installed (set FLIGHT_RIGHT_ASR_MODEL_ID)"
            return {"ok": False, "reason": reason, "error": reason}
        started = time.time()
        logprob = None
        if transcript is None:
            try:
                with self._inference_lock:
                    if clip_ref == "live-radio":
                        # Do not ask Whisper to invent text for squelch, static or silence.
                        # This gate does not alter the saved-model evaluation decoder.
                        from faster_whisper.vad import VadOptions, get_speech_timestamps
                        spans = get_speech_timestamps(audio, VadOptions(min_speech_duration_ms=100))
                        if not spans:
                            return {"ok": True, "speechDetected": False, "reason": "no speech detected in the radio segment"}
                    result = transcribe_array(self._load(), audio)
                self._error = None
            except Exception as failure:
                self._error = f"{type(failure).__name__}: {failure}"[:500]
                raise
            transcript, logprob = result["hyp"], result["avg_logprob"]
            if not transcript.strip():
                return {"ok": True, "speechDetected": False, "reason": "no intelligible speech recognised"}
        return self.process_text(transcript, flights, role=role, clip_ref=clip_ref,
                                 logprob=logprob, heard_at=heard_at, started=started, allow_apply=allow_apply,
                                 live_radio=clip_ref == "live-radio")

    def process_text(self, transcript: str, flights: list[dict], role: str = "atco",
                     clip_ref: str = "typed", logprob: float | None = None,
                     heard_at: float | None = None, started: float | None = None,
                     allow_apply: bool = True, review_of: int | None = None, live_radio: bool = False) -> dict[str, Any]:
        """One explicit speaker per transmission. Pilot speech cannot issue a clearance."""
        from ml_pipeline.voice.transcribe import ASR_VERSION
        if role not in ("auto", "pilot", "atco", "unknown"):
            raise ValueError("speaker must be auto, pilot, atco or unknown")
        transcript = transcript.strip()
        if not transcript or len(transcript) > 2000:
            raise ValueError("send between 1 and 2000 characters")
        started = started or time.time()
        asr_confidence = asr_confidence_from_logprob(logprob)
        reviewed = clip_ref in ("typed", "reviewed-radio")
        model_id = ("manual-text" if clip_ref == "typed" else "reviewed-radio") if reviewed else ASR_MODEL_ID or "cached"
        transcription_id = database.record_transcription({
            "clip_ref": f"{role}:{clip_ref}", "heard_at": heard_at, "transcript": transcript,
            "model_id": model_id, "quantisation": ASR_QUANTISATION if not reviewed else None,
            "asr_version": ASR_VERSION, "confidence": asr_confidence})
        parse_text = re.sub(r"\bFL\s*(\d{2,3})\b", r"flight level \1", transcript, flags=re.I)
        extracted = extract(parse_text, asr_confidence)
        visible = [str(f.get("callsign") or "").strip() for f in flights if f.get("callsign")]
        snapped = match(extracted.text, visible) if visible else {"code": None, "score": 0.0, "margin": 0.0}
        # Typed callsigns are often written as IGO086 rather than their spoken form.
        exact = [code for code in visible if re.search(rf"(?<!\w){re.escape(code)}(?!\w)", transcript, re.I)]
        if len(exact) == 1:
            snapped = {"code": exact[0], "score": 100.0, "margin": 100.0}
            if reviewed:
                extracted.confidence = 1.0 if extracted.action else extracted.confidence
        elif len(exact) > 1:
            snapped = {"code": None, "score": 0.0, "margin": 0.0}
        if snapped["code"] and snapped["margin"] < 5:
            snapped = {**snapped, "code": None}
        role_hint = infer_role(extracted.text, snapped["code"], extracted.callsign_spoken)
        role_source = "phrase-hint" if role == "auto" else "reviewed" if reviewed else "unresolved" if role == "unknown" else "labelled-channel"
        role = role_hint["role"] if role == "auto" else role
        out: dict[str, Any] = {
            "ok": True, "transcriptionId": transcription_id, "transcript": transcript,
            "asrConfidence": asr_confidence, "extracted": extracted.to_dict(),
            "callsignMatch": {**snapped, "heard": extracted.callsign_spoken, "listSize": len(visible)},
            "clearance": None, "seconds": round(time.time() - started, 3),
            "modelId": model_id, "quantisation": ASR_QUANTISATION if not reviewed else None,
            "role": role, "clearances": [], "readback": None, "recordedAt": time.time(),
            "roleSource": role_source, "roleReason": role_hint["reason"] if role_source == "phrase-hint" else "speaker role supplied by channel or review",
            "reviewOf": review_of, "heardAt": heard_at, "liveRadio": live_radio,
        }
        with self._conversation_lock:
            if not allow_apply:
                out["reason"] = "live radio recorded; live surveillance is required before changing trajectory intent"
            elif role == "unknown":
                out["reason"] = "speaker role uncertain: review the transmission before applying extracted intent"
            elif role == "atco" and role_source == "phrase-hint":
                out["reason"] = "possible ATCO instruction; speaker hint is unvalidated and requires review before changing intent"
            elif role == "pilot":
                out["readback"] = self._check_readback(extracted, snapped, asr_confidence)
                out["reason"] = out["readback"]["reason"]
                if snapped["code"] and out["readback"]["status"] not in ("request", "unmatched", "uncertain"):
                    self._readbacks[snapped["code"]] = out["readback"]
            elif extracted.action and snapped["code"]:
                # Requests, negations and conditional instructions require review, regardless of speaker.
                groups = [GROUP.get(a["action"]) for a in extracted.all_actions or []]
                if len(groups) != len(set(groups)):
                    out["reason"] = "multiple instructions for the same control axis: review required"
                elif re.search(r"\b(unable|negative|cancel|disregard|request|if|expect|when|after)\b|\bdo not\b|\bdon'?t\b", extracted.text):
                    out["reason"] = "conditional, cancelled or negative instruction: review required"
                else:
                    confidence = extracted.confidence * (snapped["score"] / 100.0)
                    for action in extracted.all_actions or []:
                        out["clearances"].append(clearance_service.submit(
                            {"callsign": snapped["code"], **action, "confidence": round(confidence, 3),
                             "transcription_id": transcription_id}, flights,
                            source=model_id if reviewed else f"asr:{model_id}"))
                    out["clearance"] = out["clearances"][0] if out["clearances"] else None
                    if any(c["applied"] for c in out["clearances"]):
                        self._readbacks.pop(snapped["code"], None)
            elif extracted.action:
                out["reason"] = "instruction heard but no visible aircraft matched the callsign"
            else:
                out["reason"] = "no supported instruction heard; transmission recorded"
            out["seconds"] = round(time.time() - started, 3)
            self._messages.append(out)
            database.record({"level": "audit", "source": "radio", "action": f"{role} transmission",
                             "callsign": snapped["code"], "decision": (out.get("readback") or {}).get("status") or
                             ("applied" if any(c["applied"] for c in out["clearances"]) else "recorded"),
                             "modelVersion": model_id, "detail": out})
        return out

    def review(self, transcription_id: int, text: str, role: str, flights: list[dict], allow_apply: bool = True) -> dict:
        if role not in ("atco", "pilot"):
            raise ValueError("review must identify ATCO or pilot")
        with self._conversation_lock:
            original = next((m for m in self._messages if m["transcriptionId"] == transcription_id), None)
            if original is None:
                raise ValueError("transmission is no longer in this session; review it in the audit log")
            if time.time() - original["recordedAt"] > 120:
                raise ValueError("transmission is older than two minutes; stale radio intent cannot be applied")
            return self.process_text(text, flights, role=role, clip_ref="reviewed-radio", review_of=transcription_id,
                                     heard_at=original.get("heardAt"), live_radio=original.get("liveRadio", False),
                                     allow_apply=allow_apply or not original.get("liveRadio", False))

    def _check_readback(self, extracted, snapped: dict, asr_confidence: float | None) -> dict:
        code = snapped["code"]
        result = {"status": "unmatched", "callsign": code, "checkedAt": time.time(), "items": []}
        if not code:
            return {**result, "reason": "no visible aircraft matched; readback needs review"}
        if re.search(r"\b(request|requesting|would like|can we|may we)\b", extracted.text):
            return {**result, "status": "request", "reason": "pilot request recorded; awaiting an ATCO instruction"}
        if asr_confidence is not None and extracted.confidence * snapped["score"] / 100 < clearance_service.supported()["minConfidence"]:
            return {**result, "status": "uncertain", "reason": "readback confidence below the floor; review required"}
        flight_clearances = [c for cs in clearance_service.in_force().values() for c in cs if c.callsign == code]
        if not flight_clearances:
            return {**result, "status": "no_clearance", "reason": "no active ATCO clearance to compare against"}
        result["issuedAt"] = max(c.issued_at for c in flight_clearances)
        if re.search(r"\b(unable|negative|cannot|can't|can t|not)\b", extracted.text):
            return {**result, "status": "mismatch", "reason": "pilot reports unable or negative; ATCO review required"}
        heard = extracted.all_actions or []
        if not heard:
            return {**result, "status": "incomplete", "reason": "no instruction values heard in the pilot readback"}
        for action in heard:
            expected = next((c for c in flight_clearances if c.action == action["action"]), None)
            same = bool(expected and (str(expected.fix or "").lower() == str(action.get("fix") or "").lower()) and
                        (expected.value == action.get("value") or
                         (expected.action == "TURN" and abs((float(expected.value) - float(action["value"])) % 360) < 0.01)))
            result["items"].append({"heard": action, "expected": expected.to_dict() if expected else None, "matches": same})
        if not all(item["matches"] for item in result["items"]):
            return {**result, "status": "mismatch", "reason": "pilot readback differs from the active ATCO instruction"}
        missing = [c.action for c in flight_clearances if c.action not in {a["action"] for a in heard}]
        return {**result, "status": "partial" if missing else "confirmed",
                "reason": f"matching values; still awaiting {', '.join(missing)}" if missing else "pilot readback matches the active ATCO instructions"}

    def conversation(self) -> dict:
        with self._conversation_lock:
            active = clearance_service.in_force()
            issued = {c.callsign: max(x.issued_at for x in cs) for cs in active.values() for c in cs}
            self._readbacks = {code: r for code, r in self._readbacks.items()
                               if code in issued and r.get("issuedAt") == issued[code]}
            return {"ok": True, "messages": list(reversed(self._messages)),
                    "inForce": {key: [c.to_dict() for c in cs] for key, cs in active.items()},
                    "readbacks": dict(self._readbacks),
                    "supported": clearance_service.supported()}


speech_service = SpeechService()
