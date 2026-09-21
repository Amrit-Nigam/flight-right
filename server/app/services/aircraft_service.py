"""The current picture of the airspace, and how each aircraft got here.

Holds two things:

  * the latest snapshot, which is what the map and the flight list render, and
  * a rolling history per aircraft, which is what the trajectory and conflict models
    need. They want ten past states expressed as motion, so a single snapshot is not
    enough - the history is what makes the learned models usable at all.

Mode handling implements CLAUDE.md Section 3's requirement for three data modes with a
fallback: "auto" prefers live OpenSky and drops to replay the moment the feed is
unreachable or the credit reserve is hit, and says so in every response rather than
failing quietly.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import DATA_MODE, HISTORY_LENGTH
from .normalizer import from_opensky_state, is_valid
from .opensky_client import OpenSkyClient, OpenSkyUnavailable
from .replay_service import ReplayService

log = logging.getLogger("flightright.aircraft")


@dataclass
class AircraftService:
    mode: str = DATA_MODE
    opensky: OpenSkyClient = field(default_factory=OpenSkyClient)
    replay: ReplayService = field(default_factory=ReplayService)

    flights: list[dict] = field(default_factory=list)
    histories: dict[str, deque] = field(default_factory=dict)
    source: str = "none"
    provider: str = "none"
    error: str | None = None
    updated_at: str | None = None
    updates: int = 0
    # Keys present in the most recent update. A history alone is not enough to assess a
    # pair: an aircraft that has left the box still has ten past states, and pairing on
    # those would raise an alarm about two aircraft nobody is tracking any more, using
    # positions that are minutes stale.
    current_keys: set = field(default_factory=set)
    last_seen_update: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ------------------------------------------------------------------ refreshing
    def refresh(self) -> dict:
        """Pull one update from whichever provider the mode selects."""
        flights, source, error = [], "none", None

        if self.mode in ("live", "auto"):
            try:
                states = self.opensky.fetch_states()
                now = datetime.now(timezone.utc)
                flights = [a for a in (from_opensky_state(s, now) for s in states) if is_valid(a)]
                source = "live"
            except OpenSkyUnavailable as unavailable:
                error = str(unavailable)
                if self.mode == "live":
                    log.warning("Live feed unavailable and mode is 'live': %s", error)
                else:
                    log.info("Live feed unavailable, falling back to replay: %s", error)

        if not flights and self.mode in ("replay", "auto"):
            try:
                flights = [a for a in self.replay.snapshot() if is_valid(a)]
                source = "replay"
            except Exception as failure:                      # noqa: BLE001 - reported, not raised
                error = f"{error + '; ' if error else ''}replay failed: {failure}"
                log.error("Replay failed: %s", failure)

        with self._lock:
            self.flights = flights
            self.source = source
            self.provider = {"live": "opensky", "replay": "recorded session"}.get(source, "none")
            self.error = error
            self.updated_at = datetime.now(timezone.utc).isoformat()
            self.updates += 1
            self._record_history(flights)
        return self.snapshot()

    def warm_up(self) -> int:
        """Pre-fill the history from the replay's own past, so the models start ready.

        The learned models need ten past states per aircraft. A live feed has to
        accumulate those over a hundred seconds; a recorded session already contains
        them, so in replay mode there is no reason to make anyone wait. Returns the
        number of aircraft seeded.
        """
        if self.source != "replay":
            return 0
        try:
            window = self.replay.warm_history(depth=HISTORY_LENGTH // 2)
        except Exception as failure:                          # noqa: BLE001
            log.warning("History warm-up skipped: %s", failure)
            return 0
        seeded = 0
        with self._lock:
            for key, states in window.items():
                if key not in self.current_keys:
                    continue          # only deepen the past of aircraft we can see now
                buffer = deque(maxlen=HISTORY_LENGTH)
                for state in states:
                    if buffer and buffer[-1].get("timePosition") == state.get("timePosition"):
                        continue
                    buffer.append(state)
                existing = self.histories.get(key)
                if existing:
                    for state in existing:
                        if buffer and buffer[-1].get("timePosition") == state.get("timePosition"):
                            continue
                        buffer.append(state)
                self.histories[key] = buffer
                seeded += 1
        log.info("Warmed history for %d of %d visible aircraft from the recorded session",
                 seeded, len(self.current_keys))
        return seeded

    def _record_history(self, flights: list[dict]) -> None:
        """Append each aircraft's state to its own rolling window.

        Keyed on icao24, which is the airframe address and stable across a flight;
        callsigns are not, and are occasionally blank in the feed.
        """
        seen = set()
        for aircraft in flights:
            key = aircraft["icao24"] or aircraft["callsign"]
            if not key:
                continue
            seen.add(key)
            self.last_seen_update[key] = self.updates
            window = self.histories.setdefault(key, deque(maxlen=HISTORY_LENGTH))
            # Skip duplicate position reports: replay frames and OpenSky both repeat a
            # state when an aircraft has not sent a new one, and feeding the same instant
            # twice would tell the model an aircraft had stopped.
            if window and window[-1].get("timePosition") == aircraft.get("timePosition"):
                continue
            window.append(aircraft)
        self.current_keys = seen
        # Forget aircraft that have been gone for a while, so the history map does not
        # grow without limit over a long session.
        for key in [k for k in self.histories if k not in seen]:
            if self.updates - self.last_seen_update.get(key, self.updates) > 60:
                del self.histories[key]
                self.last_seen_update.pop(key, None)

    # ------------------------------------------------------------------ reading
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "ok": True,
                "count": len(self.flights),
                "mode": self.mode,
                "source": self.source,
                "provider": self.provider,
                "error": self.error,
                "updatedAt": self.updated_at,
                "updates": self.updates,
                "replay": self.replay.status() if self.source == "replay" else None,
                "creditsRemaining": self.opensky.credits_remaining,
                "flights": list(self.flights),
            }

    def history(self, key: str) -> list[dict]:
        with self._lock:
            for candidate in (key, key.lower(), key.upper()):
                if candidate in self.histories:
                    return list(self.histories[candidate])
            for aircraft in self.flights:
                if aircraft["callsign"].upper() == key.upper():
                    return list(self.histories.get(aircraft["icao24"], []))
        return []

    def histories_for_models(self) -> dict[str, list[dict]]:
        """Aircraft that are BOTH currently visible and have a long enough window.

        Both conditions matter. The window is what the learned models need; being in the
        current update is what makes the position current. Dropping the second check
        produces alarms about aircraft that left the airspace several minutes ago.
        """
        with self._lock:
            return {key: list(window) for key, window in self.histories.items()
                    if len(window) >= 10 and key in self.current_keys}

    def set_mode(self, mode: str) -> dict:
        if mode not in ("live", "replay", "auto"):
            raise ValueError(f"mode must be live, replay or auto (got {mode!r})")
        self.mode = mode
        log.info("Data mode set to %s", mode)
        return self.refresh()


aircraft_service = AircraftService()
