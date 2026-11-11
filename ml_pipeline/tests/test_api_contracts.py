"""API contracts with isolated services: no live decisions, model inference or DB writes."""
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.app.api.routes import router


class APIContractTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        module = "server.app.api.routes."
        for name in ("aircraft_service", "conflict_service", "database", "intent_service",
                     "airport_service", "clearance_service", "trajectory_service"):
            setattr(self, name, self.enterContext(patch(module + name)))
        self.flight = {"icao24": "abc123", "callsign": "TEST123", "source": "opensky",
                       "timePosition": 100}
        self.snapshot = dict(ok=True, count=1, source="live", mode="live", provider="opensky",
                             error=None, updatedAt="2026-11-11T08:00:00Z", updates=1,
                             replay=None, creditsRemaining=3000, flights=[self.flight])
        self.aircraft_service.snapshot.return_value = self.snapshot
        self.aircraft_service.data_time.return_value = 100
        self.conflict_service.engine.status.return_value = {"rule_path": "always on"}
        self.conflict_service.snapshot.return_value = {"ok": True, "active": [], "pairsAssessed": 0}
        self.database.record.return_value = 42
        self.database.count.return_value = 1
        self.database.backend.return_value = {"backend": "postgresql"}
        self.database.query.return_value = []
        self.intent_service.status.return_value = {}

    def test_live_weather_continues_when_surveillance_fails(self):
        self.snapshot.update(source="none", flights=[], count=0)
        self.airport_service.summary.return_value = {"metar": None, "metarError": "upstream timeout"}
        r = self.client.get("/api/airport")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.airport_service.summary.call_args.args[1], "live")
        self.assertEqual(r.json()["metarError"], "upstream timeout")

    def test_auto_without_surveillance_uses_live_weather(self):
        self.snapshot.update(mode="auto", source="none")
        self.airport_service.summary.return_value = {}
        self.client.get("/api/airport")
        self.assertEqual(self.airport_service.summary.call_args.args[1], "live")

    def test_auto_replay_retains_historical_weather(self):
        self.snapshot.update(mode="auto", source="replay")
        self.airport_service.summary.return_value = {}
        self.client.get("/api/airport")
        self.assertEqual(self.airport_service.summary.call_args.args[1], "replay")

    def test_health_reports_feed_failure_even_with_http_success(self):
        self.snapshot.update(source="none", count=0, error="OpenSky timeout")
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["aircraft"]["error"], "OpenSky timeout")
        self.assertEqual(r.json()["aircraft"]["count"], 0)

    def test_actions_are_audited_with_server_versions(self):
        for action in ("accept", "dismiss"):
            with self.subTest(action=action):
                r = self.client.post("/api/actions/" + action, json={
                    "callsign": "TEST123", "modelVersion": "client-provided"})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["recorded"], 42)
                self.assertEqual(self.database.record.call_args.args[0]["modelVersion"],
                                 {"rule_path": "always on"})
        self.clearance_service.submit.assert_not_called()

    def test_audit_write_and_query(self):
        r = self.client.post("/api/audit", json={"action": "isolated test"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["entry"], 42)
        r = self.client.get("/api/audit?search=TEST123&limit=5")
        self.assertEqual(r.status_code, 200)
        self.database.query.assert_called_once_with(limit=5, level=None, conflict_id=None, search="TEST123")

    def test_mode_validation_and_intent_start(self):
        self.aircraft_service.set_mode.side_effect = ValueError("invalid mode")
        self.assertEqual(self.client.post("/api/aircraft/mode", json={"mode": "invalid"}).status_code, 400)
        self.database.record.assert_not_called()
        self.aircraft_service.set_mode.side_effect = None
        self.assertEqual(self.client.post("/api/aircraft/mode", json={"mode": "live"}).status_code, 200)
        self.intent_service.start_live.assert_called_once()

    def test_refresh_and_assessment_return_results(self):
        self.aircraft_service.refresh.return_value = self.snapshot
        self.conflict_service.assess.return_value = {"ok": True, "pairsAssessed": 1}
        self.assertEqual(self.client.post("/api/aircraft/refresh").json()["source"], "live")
        self.assertEqual(self.client.post("/api/predict/conflicts").json()["pairsAssessed"], 1)

    def test_resolution_found_and_not_found(self):
        self.assertEqual(self.client.get("/api/recommend/resolution?pair=TEST123-TEST456").status_code, 404)
        self.conflict_service.snapshot.return_value = {"active": [{"id": "TEST123-TEST456",
            "pair": ["TEST123", "TEST456"], "resolution": {"offered": False, "options": []}}]}
        r = self.client.get("/api/recommend/resolution?pair=test123-test456")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["options"], [])

    def test_trajectory_excludes_other_sources_and_future_reports(self):
        self.aircraft_service.history.return_value = [self.flight,
            {**self.flight, "source": "replay"}, {**self.flight, "timePosition": 101}]
        self.clearance_service.in_force.return_value = {}
        self.trajectory_service.predict.return_value = {"status": "warming"}
        r = self.client.get("/api/aircraft/trajectory?icao24=TEST123")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "warming")
        self.assertEqual(self.trajectory_service.predict.call_args.args[1], [self.flight])
        self.assertEqual(self.client.get("/api/aircraft/trajectory?icao24=absent").status_code, 404)

    def test_clearance_rejection_and_withdrawal_preserve_history(self):
        self.clearance_service.submit.return_value = {"ok": False, "problems": ["invalid instruction"]}
        r = self.client.post("/api/clearances", json={"callsign": "TEST123", "action": "TURN", "value": 999})
        self.assertEqual(r.status_code, 422)
        self.clearance_service.submit.return_value = {"ok": True, "applied": True}
        self.assertEqual(self.client.post("/api/clearances", json={"callsign": "TEST123"}).status_code, 200)
        self.clearance_service.clear.return_value = 1
        self.assertEqual(self.client.delete("/api/clearances?icao24=abc123").json()["withdrawn"], 1)
        self.clearance_service.clear.assert_called_once_with("abc123")

    def test_required_parameters_and_limits(self):
        for path in ("/api/aircraft/history", "/api/aircraft/trajectory", "/api/recommend/resolution",
                     "/api/audit?limit=0", "/api/conflicts/history?limit=0", "/api/clearances?limit=0"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 422)


if __name__ == "__main__":
    unittest.main()
