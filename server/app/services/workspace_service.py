"""Persistent demonstration workflow. Recorded events never authorize aircraft movement."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..config import AUDIT_DATABASE
from .database import DEFAULT_USER

POSITIONS = ("clearance", "ground", "tower")
STAGES = {
    "clearance": ("pending", "clearance recorded", "ready for ground"),
    "ground": ("pushback recorded", "taxi recorded", "holding point", "taxi in", "parked"),
    "tower": ("arrival expected", "final approach", "line up recorded", "takeoff recorded", "airborne", "landed"),
}


class WorkflowConflict(ValueError):
    pass


class WorkspaceService:
    def __init__(self, path=None):
        self.path = Path(path or AUDIT_DATABASE.with_name("workspace.sqlite3"))

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("CREATE TABLE IF NOT EXISTS strip_events (id INTEGER PRIMARY KEY, scope TEXT NOT NULL, aircraft TEXT NOT NULL, payload TEXT NOT NULL)")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def scope(snapshot):
        source = snapshot.get("source") or "none"
        session = (snapshot.get("replay") or {}).get("session") if source == "replay" else None
        return f"{source}:{session or 'live'}:{datetime.now(timezone.utc).date()}"

    def snapshot(self, scope):
        with self.connect() as db:
            rows = db.execute("SELECT aircraft,payload FROM strip_events WHERE scope=? ORDER BY id", (scope,)).fetchall()
        strips = {}
        for aircraft, payload in rows:
            strips[aircraft] = json.loads(payload)
        return {"ok": True, "scope": scope, "strips": strips, "stages": STAGES,
                "identity": DEFAULT_USER, "store": "local SQLite workflow event journal"}

    def apply(self, scope, aircraft, callsign, change):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM strip_events WHERE scope=? AND aircraft=? ORDER BY id DESC LIMIT 1", (scope, aircraft)).fetchone()
            state = json.loads(row[0]) if row else {"version": 0, "owner": None, "pending": None, "stage": "unassigned", "history": [], "note": "", "runway": "", "taxiRoute": "", "plannedRoute": ""}
            if change.version != state["version"]:
                raise WorkflowConflict("Strip changed at another position. Refresh and retry.")
            role, action = change.position, change.action
            if action == "claim":
                if state["owner"] is not None:
                    raise WorkflowConflict("This strip is already owned; request a handoff.")
                state["owner"] = role
            elif action == "acknowledge":
                if state["pending"] != role:
                    raise WorkflowConflict("No handoff is pending for this position.")
                state.update(owner=role, pending=None)
            else:
                if state["owner"] != role:
                    raise WorkflowConflict("Assume this strip or acknowledge its handoff first.")
                if action == "handoff":
                    if change.target not in POSITIONS or change.target == role or state["pending"]:
                        raise WorkflowConflict("Choose another position; cancel any existing handoff first.")
                    state["pending"] = change.target
                elif action == "cancel handoff":
                    state["pending"] = None
                elif action == "stage":
                    if change.value not in STAGES[role]:
                        raise ValueError("Stage is not available to this position.")
                    state["stage"] = change.value
                elif action == "annotate":
                    for key in ("note", "runway", "taxiRoute", "plannedRoute"):
                        state[key] = getattr(change, key)
                else:
                    raise ValueError("Unknown workflow action")
            at = datetime.now(timezone.utc).isoformat()
            state.update(version=state["version"] + 1, callsign=callsign, updatedAt=at)
            state["history"] = (state["history"] + [{"at": at, "position": role, "user": DEFAULT_USER,
                "action": action, "value": change.value, "target": change.target}])[-100:]
            db.execute("INSERT INTO strip_events(scope,aircraft,payload) VALUES(?,?,?)", (scope, aircraft, json.dumps(state)))
        return {"ok": True, "strip": state}


workspace_service = WorkspaceService()
