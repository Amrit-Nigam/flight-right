"""The level each aircraft's crew has dialled into the autopilot, for the conflict classifier.

Plan 9.0, served from 26 Sep at Archit's decision. The conflict classifier now takes three
dialled-level inputs (train_xgboost.INTENT_COLUMNS); this service supplies them at run time,
looked up per aircraft (icao24) strictly BACKWARD in time and no older than five minutes --
the same rule the training data was built with (context_features.MAX_AGE_S), so the model sees
at run time what it saw in training.

Two sources, in order:
- LIVE: adsb.lol's public API around Mumbai (https://api.adsb.lol/v2/point/<VABB>/250), polled
  every POLL_SECONDS on a background thread while the backend is in live or auto mode. Measured
  26 Sep: 33 of 38 aircraft in range carried nav_altitude_mcp.
- RECORDED: ml_pipeline/data/adsblol/intent.parquet, the adsb.lol history fetched on 25 Sep for
  every aircraft-day in our 35 OpenSky sessions (plan 9.0), so replay mode gets the dialled levels
  those aircraft actually broadcast at the time.

Data licence: adsb.lol data is ODbL 1.0 -- attribution is required and is shown by /api/health.
A missing value is returned as None and reaches the model as NaN, which XGBoost treats as
"unknown", exactly as 60% of the training encounters had it. Nothing here can raise an alarm on
its own; it only informs the classifier.
"""
from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np

from ..config import PROJECT_ROOT

log = logging.getLogger("flightright.intent")

VABB = (19.0887, 72.8679)
RADIUS_NM = 250
POLL_SECONDS = 30.0
MAX_AGE_S = 300.0
LIVE_URL = f"https://api.adsb.lol/v2/point/{VABB[0]}/{VABB[1]}/{RADIUS_NM}"
RECORDED = PROJECT_ROOT / "ml_pipeline" / "data" / "adsblol" / "intent.parquet"
HEADERS = {"User-Agent": "FlightRight-research/1.0 (academic project; polls every 30 s)"}
ATTRIBUTION = "Dialled (selected) altitude: adsb.lol, ODbL 1.0"


class IntentService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._live: dict[str, list[tuple[float, float]]] = {}
        self._recorded: dict[str, tuple[np.ndarray, np.ndarray]] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.last_poll: dict = {"ok": None, "at": None, "aircraft": 0, "with_selected_altitude": 0, "error": None}
        self.lookups = {"asked": 0, "found": 0}

    # ------------------------------------------------------------------ recorded
    def _load_recorded(self) -> dict[str, tuple[np.ndarray, np.ndarray]]:
        if self._recorded is None:
            table: dict[str, tuple[np.ndarray, np.ndarray]] = {}
            if RECORDED.exists():
                import pandas as pd
                frame = pd.read_parquet(RECORDED, columns=["icao24", "time", "nav_altitude_mcp"])
                frame = frame.dropna(subset=["nav_altitude_mcp"]).sort_values(["icao24", "time"])
                for icao24, group in frame.groupby("icao24", sort=False):
                    table[str(icao24).lower()] = (group["time"].to_numpy(np.float64),
                                                  group["nav_altitude_mcp"].to_numpy(np.float64))
                log.info("Dialled levels: %d aircraft from %s", len(table), RECORDED.name)
            else:
                log.warning("No recorded dialled levels at %s; replay runs without them", RECORDED)
            self._recorded = table
        return self._recorded

    # ------------------------------------------------------------------ live
    def start_live(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_forever, name="adsblol-intent", daemon=True)
        self._thread.start()

    def stop_live(self) -> None:
        self._stop.set()

    def _poll_forever(self) -> None:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
        while not self._stop.is_set():
            try:
                with urllib.request.urlopen(urllib.request.Request(LIVE_URL, headers=HEADERS),
                                            context=context, timeout=20) as response:
                    payload = json.load(response)
                now = float(payload.get("now", time.time() * 1000)) / 1000.0
                aircraft = payload.get("ac") or []
                count = 0
                with self._lock:
                    for ac in aircraft:
                        level = ac.get("nav_altitude_mcp")
                        if level is None or not ac.get("hex"):
                            continue
                        count += 1
                        seen = now - float(ac.get("seen") or 0.0)
                        history = self._live.setdefault(str(ac["hex"]).lower().lstrip("~"), [])
                        history.append((seen, float(level)))
                        del history[:-40]              # 40 polls = 20 minutes, plenty for a 5 min window
                self.last_poll = {"ok": True, "at": now, "aircraft": len(aircraft),
                                  "with_selected_altitude": count, "error": None}
            except Exception as failure:              # noqa: BLE001 -- a missed poll only means "unknown"
                self.last_poll = {**self.last_poll, "ok": False, "error": f"{type(failure).__name__}: {failure}"[:200]}
            self._stop.wait(POLL_SECONDS)

    # ------------------------------------------------------------------ lookup
    def selected_altitude_ft(self, icao24: str, at_time: float | None) -> float | None:
        """The dialled level reported at or before at_time, no older than five minutes."""
        if at_time is None or not icao24:
            return None
        key = str(icao24).lower()
        self.lookups["asked"] += 1
        with self._lock:
            live = [v for t, v in self._live.get(key, ()) if at_time - MAX_AGE_S <= t <= at_time + 1.0]
        if live:
            self.lookups["found"] += 1
            return live[-1]
        times, levels = self._load_recorded().get(key, (None, None))
        if times is None:
            return None
        index = int(np.searchsorted(times, at_time, side="right")) - 1
        if index >= 0 and at_time - times[index] <= MAX_AGE_S:
            self.lookups["found"] += 1
            return float(levels[index])
        return None

    def status(self) -> dict:
        asked = max(1, self.lookups["asked"])
        return {"attribution": ATTRIBUTION, "live_polling": bool(self._thread and self._thread.is_alive()),
                "last_poll": self.last_poll, "recorded_aircraft": len(self._recorded or {}),
                "lookups": self.lookups, "found_share": round(self.lookups["found"] / asked, 3)}


intent_service = IntentService()
