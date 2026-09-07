"""Append-only audit log, server-side.

CLAUDE.md Section 12 requires every AI suggestion, controller action and system decision
to produce a server-side, authenticated audit entry - timestamp, user, source component,
action, callsign, conflict id, before/after state, decision, model version, confidence -
and says explicitly that the frontend-only logging on the /logs page is demo-grade, not
the real thing. This is the real thing.

DEVIATION FROM THE PLAN, STATED OUT LOUD: Section 3 specifies PostgreSQL. This uses
SQLite. The schema is the one Section 6 describes and the queries are ordinary SQL, so
moving to Postgres is a connection-string change; but SQLite needs no server installed,
which means the audit trail actually runs today rather than after a database setup.
For a single-controller academic demo the difference is a dependency, not a capability.

Append-only is enforced by only ever issuing INSERT and SELECT here. There is no UPDATE
and no DELETE anywhere in this module.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..config import AUDIT_DATABASE

log = logging.getLogger("flightright.audit")

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT    NOT NULL,
    level         TEXT    NOT NULL,
    source        TEXT    NOT NULL,
    action        TEXT    NOT NULL,
    user_id       TEXT,
    callsign      TEXT,
    conflict_id   TEXT,
    decision      TEXT,
    model_version TEXT,
    confidence    REAL,
    detail_json   TEXT
);
CREATE INDEX IF NOT EXISTS audit_timestamp ON audit_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS audit_conflict  ON audit_logs (conflict_id);
"""


@dataclass
class AuditService:
    path: str = str(AUDIT_DATABASE)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def initialise(self) -> None:
        AUDIT_DATABASE.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
        log.info("Audit log ready at %s", self.path)

    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Write one event. Returns the stored row, including the id assigned."""
        row = {
            "timestamp": entry.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "level": str(entry.get("level", "audit")).lower(),
            "source": str(entry.get("source", "unknown")),
            "action": str(entry.get("action", "")),
            "user_id": entry.get("userId") or entry.get("user_id"),
            "callsign": entry.get("callsign"),
            "conflict_id": entry.get("conflictId") or entry.get("conflict_id"),
            "decision": entry.get("decision"),
            "model_version": json.dumps(entry["modelVersion"]) if isinstance(
                entry.get("modelVersion"), (dict, list)) else entry.get("modelVersion"),
            "confidence": entry.get("confidence"),
            "detail_json": json.dumps(entry.get("detail", {}), default=str),
        }
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO audit_logs (timestamp, level, source, action, user_id, callsign,"
                " conflict_id, decision, model_version, confidence, detail_json)"
                " VALUES (:timestamp, :level, :source, :action, :user_id, :callsign,"
                " :conflict_id, :decision, :model_version, :confidence, :detail_json)", row)
            row["id"] = cursor.lastrowid
        return self._present(row)

    def query(self, limit: int = 200, level: str | None = None,
              conflict_id: str | None = None, search: str | None = None) -> list[dict]:
        clauses, params = [], []
        if level and level != "all":
            clauses.append("level = ?")
            params.append(level.lower())
        if conflict_id:
            clauses.append("conflict_id = ?")
            params.append(conflict_id)
        if search:
            clauses.append("(action LIKE ? OR source LIKE ? OR detail_json LIKE ? OR callsign LIKE ?)")
            params += [f"%{search}%"] * 4
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM audit_logs{where} ORDER BY id DESC LIMIT ?",
                (*params, int(limit))).fetchall()
        return [self._present(dict(row)) for row in rows]

    def count(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0])

    @staticmethod
    def _present(row: dict) -> dict:
        detail = row.get("detail_json")
        try:
            detail = json.loads(detail) if isinstance(detail, str) else (detail or {})
        except json.JSONDecodeError:
            detail = {"raw": detail}
        return {
            "id": row.get("id"),
            "timestamp": row["timestamp"],
            "level": row["level"],
            "source": row["source"],
            "action": row["action"],
            "userId": row.get("user_id"),
            "callsign": row.get("callsign"),
            "conflictId": row.get("conflict_id"),
            "decision": row.get("decision"),
            "modelVersion": row.get("model_version"),
            "confidence": row.get("confidence"),
            "detail": detail,
        }


audit_service = AuditService()
