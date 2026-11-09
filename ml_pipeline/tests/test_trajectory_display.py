"""Selected-flight display: rank existing candidates without changing inference."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.app.api.routes import router
from server.app.services.trajectory_service import TrajectoryService


def reports(count=10):
    return [{"icao24": "abc", "callsign": "TEST1", "lat": 19 + i / 100,
             "lng": 73, "altitudeM": 10000, "velocityMs": 200, "heading": 90,
             "verticalRateMs": 0, "timePosition": 100 + i * 10, "source": "replay"}
            for i in range(count)]


def positions(lat):
    return {label: (lat + i / 10, 74 + i / 10, 10000)
            for i, label in enumerate(("1min", "3min", "5min", "10min"))}


class TrajectoryDisplayTests(unittest.TestCase):
    def setUp(self):
        self.service = TrajectoryService()
        self.engine = Mock()
        self.engine.multipath = SimpleNamespace(version="test-model")
        self.engine.multipath_candidates.return_value = {"abc": {
            "paths": [(0.2, positions(20)), (0.6, positions(21)), (0.1, positions(22))]}}

    def test_selects_maximum_not_first_and_converts_coordinate_order(self):
        result = self.service.predict(self.engine, reports(), [])
        self.assertEqual(result["probability"], 0.6)
        self.assertEqual(result["coordinates"], [[73, 19.09], [74, 21], [74.1, 21.1],
                                                [74.2, 21.2], [74.3, 21.3]])
        self.assertEqual(result["horizonsSeconds"], [0, 60, 180, 300, 600])

    def test_clearances_use_existing_candidate_adjustment_and_invalidate_cache(self):
        self.service.predict(self.engine, reports(), [])
        instruction = ["test-clearance"]
        self.service.predict(self.engine, reports(), instruction)
        self.assertEqual(self.engine.multipath_candidates.call_count, 2)
        self.assertEqual(self.engine.multipath_candidates.call_args.kwargs["clearances"],
                         {"abc": instruction})

    def test_cache_reuses_reports_but_refreshes_on_new_position(self):
        self.service.predict(self.engine, reports(), [])
        self.service.predict(self.engine, reports(), [])
        self.assertEqual(self.engine.multipath_candidates.call_count, 1)
        self.service.predict(self.engine, reports(11), [])
        self.assertEqual(self.engine.multipath_candidates.call_count, 2)

    def test_no_invented_prediction_without_model_or_history(self):
        self.assertEqual(self.service.predict(None, reports(), [])["status"], "unavailable")
        self.assertEqual(self.service.predict(self.engine, reports(9), [])["status"], "warming")
        self.engine.multipath_candidates.assert_not_called()

    def test_invalid_candidates_and_empty_paths_are_not_drawn(self):
        self.engine.multipath_candidates.return_value = {"abc": {"paths": [
            (float("nan"), positions(20)), (0.9, positions(100)), (0.5, {})]}}
        self.assertEqual(self.service.predict(self.engine, reports(), [])["status"], "unavailable")
        self.engine.multipath_candidates.return_value = {}
        self.assertEqual(self.service.predict(self.engine, reports(), [])["status"], "unavailable")


class TrajectoryAPITests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.aircraft = self.enterContext(patch("server.app.api.routes.aircraft_service"))
        self.predictor = self.enterContext(patch("server.app.api.routes.trajectory_service"))
        self.enterContext(patch("server.app.api.routes.clearance_service"))
        self.states = reports()
        self.aircraft.snapshot.return_value = {"source": "replay", "flights": [self.states[-1]]}
        self.aircraft.history.return_value = self.states
        self.predictor.predict.return_value = {"status": "ready", "probability": 0.6}

    def test_callsign_lookup_and_response_anchor(self):
        result = self.client.get("/api/aircraft/trajectory?icao24=test1").json()
        self.assertTrue(result["ok"])
        self.assertEqual(result["icao24"], "abc")
        self.assertEqual(result["timePosition"], 190)
        self.assertEqual(result["source"], "replay")

    def test_unknown_aircraft_is_not_predicted(self):
        self.assertEqual(self.client.get("/api/aircraft/trajectory?icao24=missing").status_code, 404)
        self.predictor.predict.assert_not_called()

    def test_future_and_other_source_reports_are_excluded(self):
        self.aircraft.history.return_value = self.states + [dict(self.states[-1], timePosition=500),
                                                           dict(self.states[-1], source="opensky")]
        self.client.get("/api/aircraft/trajectory?icao24=abc")
        self.assertEqual(self.predictor.predict.call_args.args[1], self.states)

    def test_prediction_failure_does_not_break_tracking(self):
        self.predictor.predict.side_effect = RuntimeError("model failed")
        response = self.client.get("/api/aircraft/trajectory?icao24=abc")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
