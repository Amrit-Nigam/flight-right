"""Conversation semantics using real extraction, clearance validation and path adjustment."""
import unittest
from unittest.mock import patch

import numpy as np

from server.app.services.speech_service import SpeechService
from server.app.services.clearance_service import ClearanceService
from ml_pipeline.utils.clearance import apply_clearance


class SpeechWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.service = SpeechService()
        self.clearances = ClearanceService()
        self.flights = [{"icao24": "abc123", "callsign": "IGO086"},
                        {"icao24": "def456", "callsign": "FDB1346"}]
        for target in ("server.app.services.speech_service.database", "server.app.services.clearance_service.database"):
            mock = self.enterContext(patch(target))
            mock.record_transcription.return_value = 12
            mock.record_clearance.return_value = 34
        self.enterContext(patch("server.app.services.speech_service.clearance_service", self.clearances))

    def send(self, text, role="atco", **kwargs):
        return self.service.process_text(text, self.flights, role=role, **kwargs)

    def test_compound_atco_clearance_reaches_trajectory_cap(self):
        result = self.send("IGO086, descend FL330 and turn heading 090")
        self.assertEqual([c["clearance"]["action"] for c in result["clearances"]], ["DESCEND", "TURN"])
        self.assertTrue(all(c["applied"] for c in result["clearances"]))
        level = self.clearances.in_force()["abc123"][0]
        paths = np.zeros((2, 4, 3)); paths[:, :, 2] = 9000
        _, adjusted, _, report = apply_clearance(np.array([.6, .4]), paths, 11000, level)
        self.assertTrue(report["applied"])
        self.assertTrue(np.all(adjusted[:, :, 2] >= 33000 / 3.28084))

    def test_readback_confirm_mismatch_and_request_do_not_issue(self):
        self.send("IGO086 descend FL330 and turn heading 090")
        original = self.clearances.in_force()
        result = self.send("descending flight level three three zero heading zero nine zero indigo zero eight six", "pilot")
        self.assertEqual(result["readback"]["status"], "confirmed")
        result = self.send("IGO086 descending flight level 310 heading 090", "pilot")
        self.assertEqual(result["readback"]["status"], "mismatch")
        self.assertTrue(any(not i["matches"] for i in result["readback"]["items"]))
        result = self.send("IGO086 requesting climb flight level 350", "pilot")
        self.assertEqual(result["readback"]["status"], "request")
        self.assertEqual(original, self.clearances.in_force())

    def test_partial_and_unable_readbacks(self):
        self.send("IGO086 descend FL330 and turn heading 090")
        self.assertEqual(self.send("IGO086 descending flight level 330", "pilot")["readback"]["status"], "partial")
        self.assertEqual(self.send("IGO086 unable descend flight level 330", "pilot")["readback"]["status"], "mismatch")

    def test_pilot_without_atco_clearance_cannot_change_paths(self):
        result = self.send("IGO086 climb flight level 350", "pilot")
        self.assertEqual(result["readback"]["status"], "no_clearance")
        self.assertEqual(self.clearances.in_force(), {})

    def test_low_confidence_audio_cannot_apply_or_confirm(self):
        result = self.send("indigo zero eight six descend flight level three three zero", clip_ref="upload", logprob=-2)
        self.assertFalse(result["clearance"]["applied"])
        self.send("IGO086 descend FL330")
        result = self.send("indigo zero eight six descending flight level three three zero", "pilot", clip_ref="upload", logprob=-2)
        self.assertEqual(result["readback"]["status"], "uncertain")

    def test_conditional_negative_ambiguous_and_unmatched_are_recorded(self):
        for text in ("IGO086 expect descend FL330", "IGO086 do not descend FL330", "IGO086 cancel heading 090",
                     "IGO086 and FDB1346 descend FL330", "unknown flight descend FL330"):
            with self.subTest(text=text):
                result = self.send(text)
                self.assertFalse(any(c["applied"] for c in result["clearances"]))

    def test_expiry_withdrawal_and_new_instruction_invalidate_readbacks(self):
        self.send("IGO086 descend FL330")
        self.send("IGO086 descending flight level 330", "pilot")
        self.assertIn("IGO086", self.service.conversation()["readbacks"])
        self.send("IGO086 descend FL310")
        self.assertEqual(self.service.conversation()["readbacks"], {})
        self.clearances.clear("abc123")
        self.assertEqual(self.service.conversation()["inForce"], {})

    def test_typed_flight_level_expands_for_extraction(self):
        result = self.send("IGO086 descend FL330")
        self.assertEqual(result["extracted"]["value"], 33000)
        self.assertEqual(result["modelId"], "manual-text")

    def test_invalid_input_and_nonfinite_duration(self):
        for text, role in (("", "atco"), ("x" * 2001, "pilot"), ("hello", "other")):
            with self.assertRaises(ValueError):
                self.send(text, role)
        result = self.clearances.submit({"callsign": "IGO086", "action": "TURN", "value": 90,
                                         "valid_seconds": float("inf")}, self.flights)
        self.assertFalse(result["applied"])

    def test_invalid_heading_and_contradictory_level_instructions(self):
        result = self.send("IGO086 turn heading 450")
        self.assertFalse(result["clearance"]["applied"])
        result = self.send("IGO086 climb flight level 350 and descend flight level 330")
        self.assertEqual(result["clearances"], [])

    def test_mixed_radio_role_uncertainty_does_not_create_clearance(self):
        for text in ("IGO086 descend flight level 330", "IGO086 radar identified descend flight level 330"):
            result = self.send(text, "auto")
            self.assertEqual(result["clearances"], [])
            self.assertEqual(result["roleSource"], "phrase-hint")
        result = self.send("descending flight level 330 indigo zero eight six", "auto")
        self.assertEqual(result["role"], "pilot")
        self.assertEqual(result["readback"]["status"], "no_clearance")

    def test_live_audio_cannot_adjust_replay_aircraft(self):
        result = self.send("IGO086 descend flight level 330", "atco", allow_apply=False)
        self.assertFalse(result["clearances"])
        self.assertIn("live surveillance", result["reason"])

    def test_captured_transmission_review_is_linked_and_expires(self):
        self.send("IGO086 descend FL330", "auto")
        result = self.service.review(12, "IGO086 descend FL330", "atco", self.flights)
        self.assertEqual(result["reviewOf"], 12)
        self.assertTrue(result["clearance"]["applied"])
        self.assertEqual(result["modelId"], "reviewed-radio")
        with patch("server.app.services.speech_service.time.time", return_value=result["recordedAt"] + 121):
            with self.assertRaises(ValueError):
                self.service.review(12, "IGO086 descend FL330", "atco", self.flights)


if __name__ == "__main__":
    unittest.main()
