"""Passive radio HTTP contracts without network, model loading or database writes."""
import io
import time
import unittest
from unittest.mock import patch

import numpy as np
import soundfile as sf
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.app.api.routes import router
from server.app.services.speech_service import SpeechService, decode_wav


def wav(seconds=1, rate=16000):
    out = io.BytesIO()
    sf.write(out, np.zeros(int(seconds * rate)), rate, format="WAV")
    return out.getvalue()


class RadioAPITests(unittest.TestCase):
    def setUp(self):
        app = FastAPI(); app.include_router(router)
        self.client = TestClient(app)
        self.aircraft = self.enterContext(patch("server.app.api.routes.aircraft_service"))
        self.aircraft.snapshot.return_value = {"source": "replay", "flights": [{"icao24": "abc", "callsign": "IGO086"}]}
        self.speech = self.enterContext(patch("server.app.api.routes.speech_service"))
        self.speech.hear.return_value = {"ok": True}
        self.speech.review.return_value = {"ok": True}

    def test_live_radio_uses_auto_role_and_cannot_apply_to_replay(self):
        response = self.client.post("/api/speech/hear?live=true", content=wav(), headers={"Content-Type": "audio/wav"})
        self.assertEqual(response.status_code, 200)
        args, kwargs = self.speech.hear.call_args
        self.assertEqual(args[1], "live-radio")
        self.assertEqual(kwargs["role"], "auto")
        self.assertFalse(kwargs["allow_apply"])

    def test_labelled_live_channel_can_apply_with_live_surveillance(self):
        self.aircraft.snapshot.return_value["source"] = "live"
        response = self.client.post(f"/api/speech/hear?live=true&role=atco&heard_at={time.time() - 2}", content=wav())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.speech.hear.call_args.kwargs["allow_apply"])
        self.assertEqual(self.speech.hear.call_args.kwargs["role"], "atco")

    def test_stale_empty_invalid_and_long_audio_are_rejected(self):
        cases = [("?live=true&heard_at=1", wav()), ("", b""), ("", b"invalid audio"), ("", wav(31)),
                 ("?role=wrong", wav())]
        for query, content in cases:
            with self.subTest(query=query, length=len(content)):
                self.assertEqual(self.client.post("/api/speech/hear" + query, content=content).status_code, 422)
        self.speech.hear.assert_not_called()

    def test_recognition_failure_is_reported_without_cached_fallback(self):
        self.speech.hear.side_effect = RuntimeError("device failed")
        self.assertEqual(self.client.post("/api/speech/hear?live=true", content=wav()).status_code, 503)
        self.assertEqual(self.speech.hear.call_count, 1)

    def test_review_cannot_override_replay_guard(self):
        response = self.client.post("/api/speech/review", json={"transcriptionId": 1, "text": "IGO086 descend FL330", "role": "atco", "live": False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.speech.review.call_args.kwargs["allow_apply"])

    def test_resample_and_duration_limit(self):
        self.assertEqual(len(decode_wav(wav(1, 48000))), 16000)
        with self.assertRaises(ValueError):
            decode_wav(wav(31))


class RadioVADTests(unittest.TestCase):
    def test_silence_is_not_transcribed(self):
        speech = SpeechService()
        with patch("server.app.services.speech_service.ASR_MODEL_ID", "test"), patch("ml_pipeline.voice.transcribe.transcribe_array") as transcribe:
            result = speech.hear(np.zeros(16000, dtype=np.float32), "live-radio", [])
        self.assertFalse(result["speechDetected"])
        transcribe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
