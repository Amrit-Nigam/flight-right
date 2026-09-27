"""Replay a recorded OpenSky session as if it were happening now.

CLAUDE.md Section 3 requires three data modes, and this is the second one: a stable,
repeatable feed for evaluation and for demos, and the fallback whenever OpenSky is down
or out of credits. It is not a simulation - every position in it is a real aircraft that
really was over Mumbai at that moment.

The recorded sessions are the only irreplaceable thing in the repository: twelve days of
credit-limited collection that the free OpenSky interface will not sell back.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from ..config import RAW_DIRECTORY, REPLAY_SEEK, REPLAY_SPEED
from .normalizer import METRES_TO_FEET, MS_TO_FPM, MS_TO_KNOTS, normalize

log = logging.getLogger("flightright.replay")

# One surveillance update is a 10-second bucket, matching the collection interval and the
# cadence the alert feed's re-announcement rules assume.
FRAME_SECONDS = 10


@dataclass
class ReplayService:
    """Serves one recorded session, advancing in real time from the moment it starts."""

    session_path: str | None = None
    frames: list[int] = field(default_factory=list, repr=False)
    by_frame: dict[int, pd.DataFrame] = field(default_factory=dict, repr=False)
    started_monotonic: float = 0.0
    start_index: int = 0
    seek_note: str | None = None
    loaded: bool = False

    def load(self, session_path=None) -> None:
        """Read one session into memory, bucketed into 10-second frames."""
        candidates = sorted(RAW_DIRECTORY.glob("*.parquet"))
        if not candidates:
            raise FileNotFoundError(
                f"No recorded sessions in {RAW_DIRECTORY}. Replay mode needs at least one.")
        path = session_path or max(candidates, key=lambda p: p.stat().st_mtime)

        frame = pd.read_parquet(path)
        frame = frame[frame[["latitude", "longitude", "velocity", "true_track"]].notna().all(axis=1)]
        frame = frame[~frame["on_ground"].fillna(True)]
        # Group by the POLL time, not by time_position. time_position is when each
        # aircraft last reported its own position, which differs per aircraft, so
        # bucketing on it scatters one snapshot across many frames -- measured on this
        # session, that gives frames holding anywhere from 1 to 166 aircraft. The fetch
        # timestamp is when we asked OpenSky, so it is the real snapshot boundary:
        # 536 frames of a steady 35 aircraft each.
        # Cast to second precision before the integer view: the column is
        # datetime64[us], so a raw astype("int64") yields microseconds and would
        # collapse the whole session into two frames.
        poll_seconds = frame["fetch_timestamp_utc"].dt.tz_localize(None).astype("datetime64[s]").astype("int64")
        frame["frame"] = (poll_seconds // FRAME_SECONDS) * FRAME_SECONDS

        self.by_frame = {int(key): group for key, group in frame.groupby("frame")}
        self.frames = sorted(self.by_frame)
        self.session_path = str(path)
        self.started_monotonic = time.monotonic()
        self.start_index = 0
        self.seek_note = None
        self.loaded = True
        if REPLAY_SEEK == "conflict":
            self._seek_to_first_encounter()
        log.info("Replay loaded %s: %d frames over %.0f minutes",
                 path.name, len(self.frames),
                 (self.frames[-1] - self.frames[0]) / 60 if len(self.frames) > 1 else 0)

    def _seek_to_first_encounter(self, lead_frames: int = 18,
                                 min_history_frames: int = 14) -> None:
        """Start the replay shortly before the session's first real encounter.

        A recorded session is 90 minutes of mostly uneventful traffic, so starting at
        frame zero usually means watching nothing happen. The lead is three minutes:
        long enough for the three-consecutive-updates rule to confirm the pair and for
        somebody to actually look at the screen before the encounter passes. The recordings do contain
        genuine encounters - a scan of six sessions found 4,049 frames where two
        en-route aircraft were predicted inside the alert volume - so this finds the
        first one and starts three minutes before it, giving the three-consecutive-updates
        rule time to confirm the pair as it develops.

        The encounter must be predicted inside the LEGAL minimum (5 NM / 1,000 ft), not
        just the wider 8 NM / 1,500 ft alert volume. Since 22 Sep a pair only alarms when
        the straight-line safety net sees the legal minimum breached or the classifier
        agrees, so seeking on the alert volume opened the demo on a legally separated
        pair (UAE325 x ABY821, 1,100 ft apart) that correctly never alarms, and the first
        real alarm arrived minutes later. This changes where playback starts, never when
        an alarm fires.

        Nothing is fabricated: this only chooses where in the real recording to begin.
        """
        import numpy as np
        from ml_pipeline.utils.cpa_conflict_detection import (
            SEPARATION_LATERAL_NM, SEPARATION_VERTICAL_FT, compute_cpa_from_states)

        for index, frame in enumerate(self.frames):
            # Skip encounters too early in the recording to have a past. The models need
            # ten prior states per aircraft, and starting on top of an encounter leaves
            # nowhere to take them from.
            if index < min_history_frames + lead_frames:
                continue
            rows = self.by_frame[frame].drop_duplicates("icao24", keep="last")
            altitude_m = rows["geo_altitude"].fillna(rows["baro_altitude"])
            rows = rows[(altitude_m * METRES_TO_FEET >= 10_000) & (rows["velocity"] > 50)]
            if len(rows) < 2:
                continue
            lat = rows["latitude"].to_numpy()
            lon = rows["longitude"].to_numpy()
            alt = altitude_m.reindex(rows.index).to_numpy()
            north = (lat[:, None] - lat[None, :]) * 111_320.0
            east = (lon[:, None] - lon[None, :]) * 111_320.0 * np.cos(np.radians(lat[:, None]))
            close = (np.hypot(north, east) / 1852.0 < 60.0) & (
                np.abs(alt[:, None] - alt[None, :]) * METRES_TO_FEET < 5000.0)
            for i, j in zip(*np.where(np.triu(close, 1))):
                a, b = rows.iloc[i], rows.iloc[j]
                state = lambda r, m: {                                    # noqa: E731
                    "latitude": float(r.latitude), "longitude": float(r.longitude),
                    "altitude_m": float(m), "velocity_ms": float(r.velocity),
                    "heading_deg": float(r.true_track),
                    "vertical_rate_ms": float(r.vertical_rate or 0.0)}
                cpa = compute_cpa_from_states(state(a, alt[i]), state(b, alt[j]))
                if (cpa["cpa_lateral_distance_nm"] < SEPARATION_LATERAL_NM
                        and cpa["cpa_vertical_separation_ft"] < SEPARATION_VERTICAL_FT):
                    self.start_index = max(0, index - lead_frames)
                    self.seek_note = (
                        f"{str(a.callsign).strip()} x {str(b.callsign).strip()} at frame {index}")
                    log.info("Replay starts %d frames before a real encounter: %s",
                             lead_frames, self.seek_note)
                    return
        log.info("No encounter inside the legal minimum found in this session; starting at the beginning.")

    def _current_frame_index(self) -> int:
        """Where the replay has got to, looping when it reaches the end."""
        if not self.frames:
            return 0
        elapsed = (time.monotonic() - self.started_monotonic) * REPLAY_SPEED
        return (self.start_index + int(elapsed // FRAME_SECONDS)) % len(self.frames)

    def snapshot(self) -> list[dict]:
        """Every aircraft visible at the current point in the replay."""
        if not self.loaded:
            self.load()
        if not self.frames:
            return []

        return self._aircraft_at(self._current_frame_index())

    @staticmethod
    def _row_to_aircraft(row, now: datetime) -> dict:
        altitude_m = row.geo_altitude if pd.notna(row.geo_altitude) else row.baro_altitude
        if pd.isna(altitude_m):
            altitude_m = 0.0
        return normalize({
            "icao24": row.icao24,
            "callsign": (str(row.callsign).strip() or str(row.icao24).upper()),
            "originCountry": row.origin_country,
            "lat": float(row.latitude),
            "lng": float(row.longitude),
            "altitudeFt": float(altitude_m) * METRES_TO_FEET,
            "speedKt": float(row.velocity or 0.0) * MS_TO_KNOTS,
            "heading": float(row.true_track or 0.0),
            "verticalRateFpm": float(row.vertical_rate or 0.0) * MS_TO_FPM,
            "onGround": bool(row.on_ground),
            # OpenSky returned squawk as null for 100% of rows across every session we
            # collected (CLAUDE.md, 30 Aug), so there is nothing to show here.
            "squawk": None,
            "timePosition": float(row.time_position),
            "source": "replay",
        }, now)

    def _aircraft_at(self, frame_index: int) -> list[dict]:
        rows = self.by_frame[self.frames[frame_index]].drop_duplicates("icao24", keep="last")
        now = datetime.now(timezone.utc)
        return [self._row_to_aircraft(row, now) for row in rows.itertuples(index=False)]

    def warm_history(self, depth: int = 12) -> dict[str, list[dict]]:
        """The frames immediately before the current one, oldest first.

        Without this the learned models sit idle for the first hundred seconds of every
        run, because they need ten past states per aircraft and a live feed supplies one
        per update. In replay the past is already on disk, so there is no reason to make
        the operator wait for it. Live mode has no equivalent and genuinely must
        accumulate.
        """
        if not self.loaded:
            self.load()
        if not self.frames:
            return {}
        current = self._current_frame_index()
        window: dict[str, list[dict]] = {}
        # No wrap-around. Frames "before" index 0 are the tail of the recording, ninety
        # minutes away and full of different aircraft; splicing those on as an aircraft's
        # recent past would hand the models a track that teleports.
        first = max(0, current - min(depth, len(self.frames)))
        for index in range(first, current):
            for aircraft in self._aircraft_at(index):
                key = aircraft["icao24"] or aircraft["callsign"]
                if key:
                    window.setdefault(key, []).append(aircraft)
        return window

    def reset_clock(self) -> None:
        """Start counting frames from now.

        load() runs before the models are loaded and the history warmed, which on this
        machine takes ten to twenty seconds. Left alone, the replay is already a couple
        of minutes past its chosen starting point by the time the server answers its
        first request, which is how the encounter it seeked to gets missed.
        """
        self.started_monotonic = time.monotonic()

    def status(self) -> dict:
        index = self._current_frame_index()
        return {
            "session": self.session_path.split("\\")[-1].split("/")[-1] if self.session_path else None,
            "frame": index,
            "frames": len(self.frames),
            "positionSeconds": (self.frames[index] - self.frames[0]) if self.frames else 0,
            # When this frame was actually recorded (the OpenSky poll time), so the dashboard
            # clock can show the recording's time instead of today's wall clock.
            "dataTimeUtc": (datetime.fromtimestamp(float(self.frames[index]), tz=timezone.utc).isoformat()
                            if self.frames else None),
            "speed": REPLAY_SPEED,
            "seekedTo": self.seek_note,
        }
