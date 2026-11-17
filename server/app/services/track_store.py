"""Observed display history; deliberately separate from model input windows."""
import json
import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from ..config import AUDIT_DATABASE


class TrackStore:
    def __init__(self, path=None):
        self.path = Path(path or AUDIT_DATABASE.with_name('tracks.sqlite3'))

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('CREATE TABLE IF NOT EXISTS observations (source TEXT, aircraft TEXT, at REAL, payload TEXT, PRIMARY KEY(source,aircraft,at))')
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, source, flights):
        rows = []
        for f in flights:
            key, at = f.get('icao24') or f.get('callsign'), f.get('timePosition')
            if key and isinstance(at, (int, float)) and math.isfinite(at):
                rows.append((source, key, at, json.dumps(f)))
        with self.connect() as db:
            db.executemany('INSERT OR IGNORE INTO observations VALUES (?,?,?,?)', rows)

    def history(self, source, key, until, limit=2000):
        # Latest continuous visit only: do not join a reused airframe's daily trips.
        with self.connect() as db:
            rows = db.execute('SELECT at,payload FROM observations WHERE source=? AND aircraft=? AND at<=? ORDER BY at DESC LIMIT ?',
                              (source, key, until, limit)).fetchall()
        visit, previous = [], None
        for at, payload in rows:
            if previous is not None and previous - at > 1800:
                break
            visit.append(json.loads(payload))
            previous = at
        return list(reversed(visit))


track_store = TrackStore()
