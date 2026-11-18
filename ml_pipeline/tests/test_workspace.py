import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pathlib import Path
from server.app.api.workspace import StripChange, router
from server.app.services.workspace_service import WorkspaceService, WorkflowConflict


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = WorkspaceService(Path(self.temp.name) / "workspace.sqlite3")

    def act(self, version, position, action, **extra):
        change = StripChange(scope="test", aircraft="abc", version=version, position=position, action=action, **extra)
        return self.service.apply("test", "abc", "TEST1", change)["strip"]

    def test_handoff_requires_receiver_and_survives_restart(self):
        self.act(0, "clearance", "claim")
        state = self.act(1, "clearance", "handoff", target="ground")
        self.assertEqual(state["owner"], "clearance")
        with self.assertRaises(WorkflowConflict):
            self.act(2, "tower", "acknowledge")
        self.act(2, "ground", "acknowledge")
        loaded = WorkspaceService(self.service.path).snapshot("test")["strips"]["abc"]
        self.assertEqual(loaded["owner"], "ground")
        self.assertEqual(len(loaded["history"]), 3)

    def test_stale_edit_and_wrong_owner_are_rejected(self):
        self.act(0, "ground", "claim")
        with self.assertRaises(WorkflowConflict):
            self.act(0, "ground", "annotate", note="stale")
        with self.assertRaises(WorkflowConflict):
            self.act(1, "tower", "annotate", note="wrong owner")
        self.assertEqual(self.service.snapshot("test")["strips"]["abc"]["version"], 1)

    def test_position_stage_validation_and_scope_isolation(self):
        self.act(0, "ground", "claim")
        with self.assertRaises(ValueError):
            self.act(1, "ground", "stage", value="airborne")
        state = self.act(1, "ground", "stage", value="holding point")
        self.assertEqual(state["stage"], "holding point")
        self.assertEqual(self.service.snapshot("other")["strips"], {})

    def test_annotation_persistence_and_cancel(self):
        self.act(0, "tower", "claim")
        self.act(1, "tower", "annotate", runway="27", note="Coordination pending")
        self.act(2, "tower", "handoff", target="ground")
        state = self.act(3, "tower", "cancel handoff")
        self.assertIsNone(state["pending"])
        self.assertEqual(state["runway"], "27")

    def test_http_rejects_stale_scope_missing_aircraft_and_invalid_role(self):
        app = FastAPI()
        app.include_router(router)
        with patch("server.app.api.workspace.workspace_service", self.service), patch("server.app.api.workspace.aircraft_service") as aircraft:
            aircraft.snapshot.return_value = {"source": "live", "flights": [{"icao24": "abc", "callsign": "TEST1"}]}
            with TestClient(app) as client:
                scope = client.get("/api/workspace").json()["scope"]
                payload = dict(scope=scope, aircraft="abc", version=0, position="tower", action="claim")
                self.assertEqual(client.post("/api/workspace/event", json={**payload, "scope": "old"}).status_code, 409)
                self.assertEqual(client.post("/api/workspace/event", json={**payload, "aircraft": "missing"}).status_code, 404)
                self.assertEqual(client.post("/api/workspace/event", json={**payload, "position": "admin"}).status_code, 422)
                self.assertEqual(client.post("/api/workspace/event", json=payload).status_code, 200)
                self.assertEqual(client.post("/api/workspace/event", json=payload).status_code, 409)
