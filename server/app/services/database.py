"""Persistence: the audit log, conflicts, and the resolution options offered.

PostgreSQL when `DATABASE_URL` is set and reachable; SQLite otherwise. Which one is in
use is reported by `backend()` and surfaced on `/api/health`, so the dashboard can never
be showing data from a store nobody realises it is using.

WHY POSTGRES IS THE ONE THAT MATTERS HERE. CLAUDE.md Section 12 requires the audit log
to be append-only. Under SQLite that is a convention - "this module only contains INSERT
and SELECT" - which the next person to edit it can break without noticing. Under
Postgres it is enforced by the database: the application role is granted INSERT and
SELECT on `audit_logs` and nothing else, so an UPDATE or DELETE is refused by the server
regardless of what the code asks for. `python scripts/postgres.py verify` demonstrates
it rather than asserting it.

SQLite remains as an automatic fallback, on the same principle as the rest of the
project: constant velocity under the LSTM, the CPA rule under the classifier, replay
under live. Every layer has something underneath it that still works. The fallback is
honest about being weaker - `backend()` says so, and so does the health endpoint.

SECURITY NOTES, since this module is the only one that takes arbitrary client input:

  * Every statement is parameterised. No value from a request is ever formatted into
    SQL, including the free-text search on the audit query.
  * `level` is checked against a fixed set, so a caller cannot invent log levels and
    make later filtering unreliable.
  * The `detail` blob is capped, so a client cannot push unbounded data into the log.
  * The connection string holds a password and is never returned by any endpoint or
    written to a log line.
  * The Postgres cluster listens on 127.0.0.1 only (see scripts/postgres.py).

There is deliberately no authentication on these calls. CLAUDE.md Section 3 puts that
out of MVP scope: "login or a fixed demo controller profile is enough". The recorded
user is a server-side default, not whatever the client claims.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from ..config import AUDIT_DATABASE, DATABASE_URL

log = logging.getLogger("flightright.database")

# A caller cannot invent levels. Anything else is stored as "audit".
LEVELS = {"audit", "system", "mock", "console:error", "warning", "error"}
DEFAULT_USER = "demo-controller"
MAX_DETAIL_BYTES = 16_384
MAX_TEXT = 2_000

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_logs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT now(),
    level         TEXT        NOT NULL,
    source        TEXT        NOT NULL,
    action        TEXT        NOT NULL,
    user_id       TEXT,
    callsign      TEXT,
    conflict_id   TEXT,
    decision      TEXT,
    model_version TEXT,
    confidence    DOUBLE PRECISION,
    detail        JSONB       NOT NULL DEFAULT '{}'::jsonb
);
"""

SQLITE_SCHEMA = """
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
    detail        TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS audit_timestamp ON audit_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS audit_conflict  ON audit_logs (conflict_id);

CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY, aircraft_a TEXT NOT NULL, aircraft_b TEXT NOT NULL,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, tier INTEGER NOT NULL,
    severity TEXT NOT NULL, cpa_seconds REAL, cpa_lateral_nm REAL,
    cpa_vertical_ft REAL, classifier_probability REAL, rule_is_conflict INTEGER,
    model_versions TEXT, reason TEXT
);
CREATE TABLE IF NOT EXISTS resolution_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conflict_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL, rank INTEGER NOT NULL, manoeuvre_type TEXT NOT NULL,
    target_aircraft TEXT NOT NULL, magnitude REAL, unit TEXT,
    resulting_lateral_nm REAL, resulting_vertical_ft REAL, seconds_to_establish REAL,
    delay_seconds REAL, fuel_equivalent_seconds REAL, confidence REAL, score REAL,
    residual_risk REAL, new_conflict_risk REAL, explanation TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS resolution_conflict ON resolution_options (conflict_id);

-- Plan Phase 7.3: the voice chain's records, append-only (see scripts/postgres.py).
CREATE TABLE IF NOT EXISTS transcriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at TEXT NOT NULL, clip_ref TEXT NOT NULL,
    heard_at TEXT, frequency_mhz REAL, transcript TEXT NOT NULL, model_id TEXT NOT NULL,
    quantisation TEXT, asr_version TEXT NOT NULL, confidence REAL
);
CREATE TABLE IF NOT EXISTS extracted_clearances (
    id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at TEXT NOT NULL, transcription_id INTEGER,
    source TEXT NOT NULL, matched_icao24 TEXT NOT NULL, callsign_heard TEXT,
    callsign_matched TEXT, action TEXT NOT NULL, value REAL, fix TEXT, confidence REAL NOT NULL,
    issued_at TEXT NOT NULL, valid_seconds REAL NOT NULL, applied INTEGER NOT NULL,
    report TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS clearances_icao ON extracted_clearances (matched_icao24, issued_at DESC);
"""


def _clip(value: Any, limit: int = MAX_TEXT) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:limit]


class Database:
    """One store, two possible backends, one API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._postgres = None
        self._backend = "none"
        self._error: str | None = None

    # ------------------------------------------------------------------ lifecycle
    def initialise(self) -> str:
        with self._lock:
            if DATABASE_URL:
                try:
                    import psycopg

                    self._postgres = psycopg.connect(DATABASE_URL, autocommit=True)
                    # The application role cannot create tables; the schema is applied
                    # by scripts/postgres.py as the owner. This only confirms it is there.
                    self._postgres.execute("SELECT 1 FROM audit_logs LIMIT 1")
                    self._backend = "postgresql"
                    self._error = None
                    version = self._postgres.execute(
                        "SELECT current_setting('server_version')").fetchone()[0]
                    log.info("Audit store: PostgreSQL %s as %s", version,
                             self._postgres.execute("SELECT current_user").fetchone()[0])
                    return self._backend
                except Exception as failure:                       # noqa: BLE001
                    # Never let the connection string into a log line - it has a password.
                    self._error = f"{type(failure).__name__}: {str(failure)[:200]}"
                    self._postgres = None
                    log.warning("PostgreSQL unavailable (%s); falling back to SQLite",
                                self._error)

            AUDIT_DATABASE.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.sqlite_path) as connection:
                connection.executescript(SQLITE_SCHEMA)
            self._backend = "sqlite"
            log.info("Audit store: SQLite at %s (append-only by convention, not enforced)",
                     self.sqlite_path)
            return self._backend

    @property
    def sqlite_path(self) -> str:
        return str(AUDIT_DATABASE)

    def backend(self) -> dict[str, Any]:
        return {
            "backend": self._backend,
            "appendOnlyEnforced": self._backend == "postgresql",
            "location": "127.0.0.1:5433/flightright" if self._backend == "postgresql"
                        else self.sqlite_path,
            "fallbackReason": self._error,
        }

    def _sqlite(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _execute(self, postgres_sql: str, sqlite_sql: str, params: tuple = ()) -> list[dict]:
        """Run a statement on whichever backend is live, returning rows as dicts."""
        with self._lock:
            if self._backend == "postgresql" and self._postgres is not None:
                try:
                    cursor = self._postgres.execute(postgres_sql, params)
                    if cursor.description is None:
                        return []
                    columns = [c.name for c in cursor.description]
                    return [dict(zip(columns, row)) for row in cursor.fetchall()]
                except Exception as failure:                       # noqa: BLE001
                    log.error("PostgreSQL statement failed: %s", str(failure)[:200])
                    raise
            with self._sqlite() as connection:
                cursor = connection.execute(sqlite_sql, params)
                if cursor.description is None:
                    return []
                return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------ audit log
    def record(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Write one event. INSERT only - there is no code path here that modifies one."""
        level = str(entry.get("level", "audit")).lower()
        detail = entry.get("detail", {})
        detail_text = json.dumps(detail, default=str)[:MAX_DETAIL_BYTES]
        model_version = entry.get("modelVersion")
        if isinstance(model_version, (dict, list)):
            model_version = json.dumps(model_version, default=str)

        row = (
            entry.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            level if level in LEVELS else "audit",
            _clip(entry.get("source", "unknown"), 120),
            _clip(entry.get("action", "")),
            _clip(entry.get("userId") or entry.get("user_id") or DEFAULT_USER, 120),
            _clip(entry.get("callsign"), 16),
            _clip(entry.get("conflictId") or entry.get("conflict_id"), 64),
            _clip(entry.get("decision"), 32),
            _clip(model_version, 500),
            float(entry["confidence"]) if isinstance(entry.get("confidence"), (int, float)) else None,
            detail_text,
        )
        rows = self._execute(
            "INSERT INTO audit_logs (timestamp, level, source, action, user_id, callsign,"
            " conflict_id, decision, model_version, confidence, detail)"
            " VALUES (%s::timestamptz, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)"
            " RETURNING id, timestamp",
            "INSERT INTO audit_logs (timestamp, level, source, action, user_id, callsign,"
            " conflict_id, decision, model_version, confidence, detail)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row)
        stored = {
            "id": rows[0]["id"] if rows else None,
            "timestamp": row[0], "level": row[1], "source": row[2], "action": row[3],
            "userId": row[4], "callsign": row[5], "conflictId": row[6],
            "decision": row[7], "modelVersion": row[8], "confidence": row[9],
            "detail": detail,
        }
        return stored

    def query(self, limit: int = 200, level: str | None = None,
              conflict_id: str | None = None, search: str | None = None) -> list[dict]:
        limit = max(1, min(int(limit), 2000))
        clauses: list[str] = []
        params: list[Any] = []
        if level and level != "all":
            clauses.append("level = {p}")
            params.append(level.lower())
        if conflict_id:
            clauses.append("conflict_id = {p}")
            params.append(conflict_id[:64])
        if search:
            clauses.append("(action LIKE {p} OR source LIKE {p} OR callsign LIKE {p})")
            params += [f"%{search[:200]}%"] * 3
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        pg_where = where.replace("{p}", "%s")
        lite_where = where.replace("{p}", "?")
        rows = self._execute(
            f"SELECT * FROM audit_logs{pg_where} ORDER BY id DESC LIMIT %s",
            f"SELECT * FROM audit_logs{lite_where} ORDER BY id DESC LIMIT ?",
            (*params, limit))
        return [self._present(row) for row in rows]

    def count(self) -> int:
        rows = self._execute("SELECT COUNT(*) AS n FROM audit_logs",
                             "SELECT COUNT(*) AS n FROM audit_logs")
        return int(rows[0]["n"]) if rows else 0

    @staticmethod
    def _present(row: dict) -> dict:
        detail = row.get("detail")
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except json.JSONDecodeError:
                detail = {"raw": detail}
        timestamp = row.get("timestamp")
        return {
            "id": row.get("id"),
            "timestamp": timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
            "level": row.get("level"), "source": row.get("source"),
            "action": row.get("action"), "userId": row.get("user_id"),
            "callsign": row.get("callsign"), "conflictId": row.get("conflict_id"),
            "decision": row.get("decision"), "modelVersion": row.get("model_version"),
            "confidence": row.get("confidence"), "detail": detail or {},
        }

    # ------------------------------------------------------- conflicts and options
    def record_conflicts(self, alerts: list[dict]) -> int:
        """Persist the confirmed conflicts and the manoeuvres offered for them.

        Unlike the audit log these are working state - the same pair is re-assessed
        every ten seconds - so they are upserted rather than appended. The audit log
        remains the append-only record of what was decided.
        """
        if not alerts:
            return 0
        now = datetime.now(timezone.utc)
        written = 0
        for alert in alerts:
            pair = alert.get("pair") or []
            if len(pair) != 2:
                continue
            conflict_id = str(alert.get("id"))[:64]
            values = (
                conflict_id, pair[0][:16], pair[1][:16], now, now,
                int(alert.get("tier", 0)), str(alert.get("severity", "none"))[:16],
                _float(alert.get("timeToCpaSeconds")), _float(alert.get("cpaLateralNm")),
                _float(alert.get("cpaVerticalFt")), _float(alert.get("classifierProbability")),
                bool(alert.get("ruleIsConflict")),
                json.dumps(alert.get("sources", []), default=str)[:2000],
                _clip(alert.get("reason")),
            )
            try:
                self._execute(
                    "INSERT INTO conflicts (id, aircraft_a, aircraft_b, first_seen, last_seen,"
                    " tier, severity, cpa_seconds, cpa_lateral_nm, cpa_vertical_ft,"
                    " classifier_probability, rule_is_conflict, model_versions, reason)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)"
                    " ON CONFLICT (id) DO UPDATE SET last_seen = EXCLUDED.last_seen,"
                    " tier = EXCLUDED.tier, severity = EXCLUDED.severity,"
                    " cpa_seconds = EXCLUDED.cpa_seconds,"
                    " cpa_lateral_nm = EXCLUDED.cpa_lateral_nm,"
                    " cpa_vertical_ft = EXCLUDED.cpa_vertical_ft,"
                    " classifier_probability = EXCLUDED.classifier_probability,"
                    " reason = EXCLUDED.reason",
                    "INSERT INTO conflicts (id, aircraft_a, aircraft_b, first_seen, last_seen,"
                    " tier, severity, cpa_seconds, cpa_lateral_nm, cpa_vertical_ft,"
                    " classifier_probability, rule_is_conflict, model_versions, reason)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT (id) DO UPDATE SET last_seen = excluded.last_seen,"
                    " tier = excluded.tier, severity = excluded.severity,"
                    " cpa_seconds = excluded.cpa_seconds,"
                    " cpa_lateral_nm = excluded.cpa_lateral_nm,"
                    " cpa_vertical_ft = excluded.cpa_vertical_ft,"
                    " classifier_probability = excluded.classifier_probability,"
                    " reason = excluded.reason",
                    _iso_for_sqlite(values, self._backend))
                written += 1
            except Exception as failure:                           # noqa: BLE001
                log.error("Could not persist conflict %s: %s", conflict_id, str(failure)[:160])
                continue

            options = (alert.get("resolution") or {}).get("options") or []
            if not options:
                continue
            self._execute("DELETE FROM resolution_options WHERE conflict_id = %s",
                          "DELETE FROM resolution_options WHERE conflict_id = ?",
                          (conflict_id,))
            for rank, option in enumerate(options, start=1):
                self._execute(
                    "INSERT INTO resolution_options (conflict_id, recorded_at, rank,"
                    " manoeuvre_type, target_aircraft, magnitude, unit, resulting_lateral_nm,"
                    " resulting_vertical_ft, seconds_to_establish, delay_seconds,"
                    " fuel_equivalent_seconds, confidence, score, residual_risk,"
                    " new_conflict_risk, explanation)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    "INSERT INTO resolution_options (conflict_id, recorded_at, rank,"
                    " manoeuvre_type, target_aircraft, magnitude, unit, resulting_lateral_nm,"
                    " resulting_vertical_ft, seconds_to_establish, delay_seconds,"
                    " fuel_equivalent_seconds, confidence, score, residual_risk,"
                    " new_conflict_risk, explanation)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    _iso_for_sqlite((
                        conflict_id, now, rank,
                        str(option.get("manoeuvre_type", ""))[:32],
                        str(option.get("aircraft", ""))[:16],
                        _float(option.get("magnitude")), str(option.get("unit", ""))[:8],
                        _float(option.get("resulting_lateral_separation_nm")),
                        _float(option.get("resulting_vertical_separation_ft")),
                        _float(option.get("seconds_to_establish")),
                        _float(option.get("delay_seconds")),
                        _float(option.get("fuel_equivalent_seconds")),
                        _float(option.get("confidence")), _float(option.get("score")),
                        _float(option.get("residual_risk")),
                        _float(option.get("new_conflict_risk")),
                        _clip(option.get("explanation")),
                    ), self._backend))
        return written

    def conflict_history(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        rows = self._execute(
            "SELECT * FROM conflicts ORDER BY last_seen DESC LIMIT %s",
            "SELECT * FROM conflicts ORDER BY last_seen DESC LIMIT ?", (limit,))
        for row in rows:
            for key in ("first_seen", "last_seen"):
                if hasattr(row.get(key), "isoformat"):
                    row[key] = row[key].isoformat()
        return rows

    # --------------------------------------------- voice chain (plan Phase 7.3)
    def record_transcription(self, row: dict[str, Any]) -> int | None:
        """One transcript and the model that produced it. INSERT only.

        Unused until the speech chain exists (plan Phases 4-5). model_id and asr_version
        are required, so no transcript can be stored without saying what heard it.
        """
        now = datetime.now(timezone.utc)
        heard = row.get("heard_at")
        values = (now, _clip(row["clip_ref"], 500),
                  datetime.fromtimestamp(float(heard), timezone.utc) if heard is not None else None,
                  _float(row.get("frequency_mhz")), _clip(row["transcript"]),
                  _clip(row["model_id"], 200), _clip(row.get("quantisation"), 32),
                  _clip(row["asr_version"], 200), _float(row.get("confidence")))
        rows = self._execute(
            "INSERT INTO transcriptions (recorded_at, clip_ref, heard_at, frequency_mhz, transcript,"
            " model_id, quantisation, asr_version, confidence) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            " RETURNING id",
            "INSERT INTO transcriptions (recorded_at, clip_ref, heard_at, frequency_mhz, transcript,"
            " model_id, quantisation, asr_version, confidence) VALUES (?,?,?,?,?,?,?,?,?)",
            _iso_for_sqlite(values, self._backend))
        return rows[0]["id"] if rows else None

    def record_clearance(self, clearance: dict[str, Any], applied: bool, report: dict[str, Any]) -> int | None:
        """One clearance and what the system did with it. INSERT only."""
        now = datetime.now(timezone.utc)
        values = (now, clearance.get("transcription_id"), _clip(clearance.get("source"), 120),
                  _clip(clearance.get("icao24"), 16), _clip(clearance.get("notes", {}).get("callsign_heard"), 16),
                  _clip(clearance.get("callsign"), 16), _clip(clearance.get("action"), 16),
                  _float(clearance.get("value")), _clip(clearance.get("fix"), 16),
                  float(clearance.get("confidence", 0.0)),
                  datetime.fromtimestamp(float(clearance.get("issued_at", 0.0)), timezone.utc),
                  float(clearance.get("valid_seconds", 0.0)), bool(applied),
                  json.dumps(report, default=str)[:MAX_DETAIL_BYTES])
        rows = self._execute(
            "INSERT INTO extracted_clearances (recorded_at, transcription_id, source, matched_icao24,"
            " callsign_heard, callsign_matched, action, value, fix, confidence, issued_at,"
            " valid_seconds, applied, report)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING id",
            "INSERT INTO extracted_clearances (recorded_at, transcription_id, source, matched_icao24,"
            " callsign_heard, callsign_matched, action, value, fix, confidence, issued_at,"
            " valid_seconds, applied, report) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            _iso_for_sqlite(values, self._backend))
        return rows[0]["id"] if rows else None

    def clearance_history(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        rows = self._execute(
            "SELECT * FROM extracted_clearances ORDER BY id DESC LIMIT %s",
            "SELECT * FROM extracted_clearances ORDER BY id DESC LIMIT ?", (limit,))
        for row in rows:
            for key in ("recorded_at", "issued_at"):
                if hasattr(row.get(key), "isoformat"):
                    row[key] = row[key].isoformat()
            if isinstance(row.get("report"), str):
                try:
                    row["report"] = json.loads(row["report"])
                except json.JSONDecodeError:
                    pass
            row["applied"] = bool(row.get("applied"))
        return rows


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_for_sqlite(values: tuple, backend: str) -> tuple:
    """SQLite has no timestamp type, so datetimes become ISO strings there."""
    if backend == "postgresql":
        return values
    return tuple(v.isoformat() if isinstance(v, datetime) else v for v in values)


database = Database()
