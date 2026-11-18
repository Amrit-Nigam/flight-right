"""Mumbai airport (VABB): its real runways, its real weather report, and what the traffic shows.

Replaces three things the dashboard used to invent (ISSUES.md, "Hardcoded values"): the top
bar's "ATIS M / RWY 27R 27L", the flight list's fixed METAR, and the runway panel's scheduled
slots on runways Mumbai does not have. Everything here is either published data or derived
from the aircraft we actually see, and says which.

Sources, stated because a mentor will ask:
- Runways: OurAirports runways.csv (public domain), https://ourairports.com/data/ -- VABB has
  09/27 and 14/32, with the coordinates of each threshold. There is no 27L/27R.
- METAR (the official half-hourly airport weather report):
    live   -> aviationweather.gov data API (NOAA), https://aviationweather.gov/data/api/
    replay -> the Iowa Environmental Mesonet ASOS/METAR archive,
              https://mesonet.agron.iastate.edu/request/download.phtml, cached on disk by
              scripts/fetch_metar_archive.py so a replay needs no internet.
- Runway in use and runway movements: DERIVED from the tracks. An aircraft low, slow-ish and
  lined up with a runway end is landing on it; one climbing away along it has departed from
  it. When no movement has been seen yet, the runway most into the METAR surface wind is
  shown, and labelled as such. ATIS letters are not published anywhere we can read, so none
  is shown.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import PROJECT_ROOT

log = logging.getLogger("flightright.airport")

ICAO = "VABB"
ARP = (19.0887, 72.8679)                      # aerodrome reference point (OurAirports)
ROUTES_DIR = PROJECT_ROOT / "ml_pipeline" / "data" / "routes"
WEATHER_DIR = PROJECT_ROOT / "ml_pipeline" / "data" / "weather"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"
LIVE_METAR_URL = f"https://aviationweather.gov/api/data/metar?ids={ICAO}&format=json&hours=3"
IEM_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
HEADERS = {"User-Agent": "FlightRight-research/1.0 (academic project; cached)"}

# Movement detection, our own design (no source): thresholds chosen from what a landing and a
# departure look like in ADS-B, and deliberately conservative -- an unclassified aircraft is
# simply not counted.
LANDING_MAX_FT = 2_000.0          # below this near a threshold
LANDING_MAX_NM = 6.0              # from that threshold, on the approach side
DEPARTURE_MAX_FT = 4_000.0        # climbing away below this
DEPARTURE_MAX_NM = 8.0            # from the runway's far threshold
ALIGN_DEG = 20.0                  # track within this of the runway heading
ARRIVAL_HORIZON_NM = 45.0         # upcoming arrivals considered within this range
EVENT_WINDOW_S = 45 * 60          # "recent" movements
METAR_MAX_AGE_S = 90 * 60         # an older report is shown as stale


def _context() -> ssl.SSLContext:
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


def _get(url: str, timeout: float = 20.0) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), context=_context(),
                                timeout=timeout) as response:
        return response.read()


def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return 3440.065 * math.acos(max(-1.0, min(1.0, c)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    return math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                   math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) % 360.0


def angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


# ---------------------------------------------------------------------------------- runways
def load_runways() -> list[dict]:
    """VABB's runways from OurAirports: one entry per runway END (the direction you land on)."""
    path = ROUTES_DIR / "ourairports_runways.csv"
    if not path.exists():
        ROUTES_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_get(RUNWAYS_URL, timeout=120))
    ends = []
    for row in csv.DictReader(io.StringIO(path.read_text(encoding="utf8"))):
        if row["airport_ident"] != ICAO or row.get("closed") == "1":
            continue
        le = (float(row["le_latitude_deg"]), float(row["le_longitude_deg"]))
        he = (float(row["he_latitude_deg"]), float(row["he_longitude_deg"]))
        pair = f"{row['le_ident']}/{row['he_ident']}"
        length_ft = int(float(row["length_ft"] or 0))
        # Heading of each end = the direction an aircraft rolls when using it.
        ends.append({"end": row["le_ident"], "runway": pair, "threshold": le, "far": he,
                     "heading": bearing_deg(*le, *he), "lengthFt": length_ft})
        ends.append({"end": row["he_ident"], "runway": pair, "threshold": he, "far": le,
                     "heading": bearing_deg(*he, *le), "lengthFt": length_ft})
    return ends


# ---------------------------------------------------------------------------------- METAR
_WIND = re.compile(r"\b(?P<dir>\d{3}|VRB)(?P<spd>\d{2,3})(?:G(?P<gust>\d{2,3}))?KT\b")
_VIS = re.compile(r"\s(?P<vis>\d{4})\s")
_TEMP = re.compile(r"\s(?P<t>M?\d{2})/(?P<d>M?\d{2})?\s")
_QNH = re.compile(r"\sQ(?P<q>\d{4})\b")
_CLOUD = re.compile(r"\b(?P<cov>FEW|SCT|BKN|OVC|VV)(?P<base>\d{3})(?P<type>CB|TCU)?\b")
_WX = re.compile(r"(?<=\s)(?P<wx>[-+]?(?:VC)?(?:MI|BC|PR|DR|BL|SH|TS|FZ)?(?:DZ|RA|SN|SG|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|SQ|FC|SS|DS)+)(?=\s)")


def parse_metar(raw: str) -> dict:
    """The parts of a METAR a controller glances at, decoded. Anything absent stays None."""
    text = f" {raw.strip()} "
    body = text.split(" NOSIG")[0].split(" TEMPO")[0].split(" BECMG")[0]
    wind = _WIND.search(body)
    vis = _VIS.search(body.split("KT", 1)[-1] if "KT" in body else body)
    temp = _TEMP.search(body)
    qnh = _QNH.search(body)
    signed = lambda s: None if s is None else (-int(s[1:]) if s.startswith("M") else int(s))  # noqa: E731
    return {
        "windDirDeg": None if not wind or wind["dir"] == "VRB" else int(wind["dir"]),
        "windVariable": bool(wind and wind["dir"] == "VRB"),
        "windKt": int(wind["spd"]) if wind else None,
        "gustKt": int(wind["gust"]) if wind and wind["gust"] else None,
        "visibilityM": (10_000 if " CAVOK " in body else int(vis["vis"])) if (vis or " CAVOK " in body) else None,
        "weather": [m["wx"] for m in _WX.finditer(body.split("KT", 1)[-1])] if wind else [],
        "clouds": [{"cover": m["cov"], "baseFt": int(m["base"]) * 100, "type": m["type"]} for m in _CLOUD.finditer(body)],
        "tempC": signed(temp["t"]) if temp else None,
        "dewpointC": signed(temp["d"]) if temp and temp["d"] else None,
        "qnhHpa": int(qnh["q"]) if qnh else None,
    }


class MetarArchive:
    """Half-hourly METARs for VABB, cached on disk; fetched per UTC day when missing."""

    def __init__(self) -> None:
        self.path = WEATHER_DIR / f"metar_{ICAO}.csv"
        self._rows: list[tuple[float, str]] | None = None
        self._days_tried: set[str] = set()
        self._lock = threading.Lock()

    def _load(self) -> list[tuple[float, str]]:
        if self._rows is None:
            rows = []
            if self.path.exists():
                for line in self.path.read_text(encoding="utf8").splitlines()[1:]:
                    parts = line.split(",", 2)
                    if len(parts) == 3 and parts[2].strip():
                        stamp = datetime.strptime(parts[1], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                        rows.append((stamp.timestamp(), parts[2].strip()))
            self._rows = sorted(set(rows))
        return self._rows

    @staticmethod
    def _fetch_day(day: datetime) -> str:
        """One UTC day from IEM. The service resets long multi-week requests, so it is asked a
        day at a time, politely, with a couple of retries."""
        after = day + timedelta(days=1)
        query = {"station": ICAO, "data": "metar", "tz": "Etc/UTC", "format": "onlycomma", "latlon": "no",
                 "missing": "M", "trace": "T", "direct": "no", "report_type": ["3", "4"],
                 "year1": day.year, "month1": day.month, "day1": day.day,
                 "year2": after.year, "month2": after.month, "day2": after.day}
        for attempt in range(3):
            try:
                return _get(f"{IEM_URL}?{urllib.parse.urlencode(query, doseq=True)}", timeout=60).decode("utf8")
            except Exception:                      # noqa: BLE001
                if attempt == 2:
                    raise
                time.sleep(2 + 3 * attempt)
        return ""

    def fetch_days(self, first: datetime, last: datetime) -> int:
        """Download the IEM archive for every UTC date in [first, last] and merge it into the cache."""
        day = datetime(first.year, first.month, first.day, tzinfo=timezone.utc)
        end = datetime(last.year, last.month, last.day, tzinfo=timezone.utc)
        text = ""
        while day <= end:
            text += self._fetch_day(day)
            day += timedelta(days=1)
            time.sleep(1.0)
        new = []
        for line in text.splitlines():
            parts = line.split(",", 2)
            if len(parts) == 3 and parts[0] == ICAO and parts[2] not in ("", "M"):
                stamp = datetime.strptime(parts[1], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                new.append((stamp.timestamp(), parts[2].strip()))
        with self._lock:
            rows = sorted(set(self._load() + new))
            WEATHER_DIR.mkdir(parents=True, exist_ok=True)
            self.path.write_text("station,valid,metar\n" + "".join(
                f"{ICAO},{datetime.fromtimestamp(t, tz=timezone.utc):%Y-%m-%d %H:%M},{m}\n" for t, m in rows),
                encoding="utf8")
            self._rows = rows
        return len(new)

    def at(self, when: float) -> dict | None:
        """The latest report issued at or before `when` (epoch seconds, UTC)."""
        rows = self._load()
        day = datetime.fromtimestamp(when, tz=timezone.utc).strftime("%Y-%m-%d")
        if not any(abs(t - when) < 86_400 for t, _ in rows) and day not in self._days_tried:
            self._days_tried.add(day)            # one attempt per day; a replay must not hang on it
            try:
                d = datetime.fromtimestamp(when, tz=timezone.utc)
                self.fetch_days(d - timedelta(days=1), d)
                rows = self._load()
            except Exception as failure:          # noqa: BLE001 -- no network: report "unavailable"
                log.info("METAR archive fetch for %s failed: %s", day, failure)
        best = None
        for t, raw in rows:
            if t <= when + 60:
                best = (t, raw)
            else:
                break
        if best is None:
            return None
        return {"raw": best[1], "issuedUtc": datetime.fromtimestamp(best[0], tz=timezone.utc).isoformat(),
                "ageSeconds": round(when - best[0]), "stale": when - best[0] > METAR_MAX_AGE_S,
                "source": "Iowa Environmental Mesonet METAR archive", **parse_metar(best[1])}


class LiveMetar:
    """The current METAR from aviationweather.gov, re-read at most every five minutes."""

    def __init__(self) -> None:
        self._cached: tuple[float, dict | None] = (0.0, None)
        self.error: str | None = None

    def current(self) -> dict | None:
        fetched_at, value = self._cached
        if time.time() - fetched_at < 300:
            return value
        try:
            import json
            reports = json.loads(_get(LIVE_METAR_URL))
            latest = max(reports, key=lambda r: r.get("obsTime", 0)) if reports else None
            if latest:
                raw = str(latest.get("rawOb", "")).replace("METAR ", "", 1)
                value = {"raw": raw, "issuedUtc": datetime.fromtimestamp(latest["obsTime"], tz=timezone.utc).isoformat(),
                         "ageSeconds": round(time.time() - latest["obsTime"]),
                         "stale": time.time() - latest["obsTime"] > METAR_MAX_AGE_S,
                         "source": "aviationweather.gov (NOAA) live METAR", **parse_metar(raw)}
            self.error = None
        except Exception as failure:              # noqa: BLE001
            self.error = f"{type(failure).__name__}: {failure}"[:160]
        self._cached = (time.time(), value)
        return value


# ---------------------------------------------------------------------------------- movements
class AirportService:
    def __init__(self) -> None:
        self.archive = MetarArchive()
        self.live = LiveMetar()
        self._ends: list[dict] | None = None
        self.events: dict[tuple[str, str], dict] = {}     # (icao24, kind) -> latest movement
        self._lock = threading.Lock()

    @property
    def ends(self) -> list[dict]:
        if self._ends is None:
            try:
                self._ends = load_runways()
            except Exception as failure:          # noqa: BLE001
                log.warning("Runway data unavailable: %s", failure)
                self._ends = []
        return self._ends

    def metar(self, source: str, data_time: float) -> dict | None:
        return self.live.current() if source == "live" else self.archive.at(data_time)

    def _classify(self, state: dict) -> tuple[str, dict] | None:
        """('landing'|'departure', runway end) for one state, or None."""
        lat, lng = state.get("lat"), state.get("lng")
        alt, track = float(state.get("altitudeFt") or 0), float(state.get("heading") or 0)
        vs = float(state.get("verticalRateFpm") or 0)
        if lat is None or lng is None or state.get("onGround"):
            return None
        for end in self.ends:
            if angle_diff(track, end["heading"]) > ALIGN_DEG:
                continue
            to_threshold = distance_nm(lat, lng, *end["threshold"])
            ahead = angle_diff(bearing_deg(lat, lng, *end["threshold"]), track) < 30
            if alt < LANDING_MAX_FT and to_threshold < LANDING_MAX_NM and ahead and vs <= 200:
                return "landing", end
            from_far = distance_nm(lat, lng, *end["far"])
            behind = angle_diff(bearing_deg(*end["far"], lat, lng), track) < 30
            if alt < DEPARTURE_MAX_FT and from_far < DEPARTURE_MAX_NM and behind and vs > 300:
                return "departure", end
        return None

    def observe(self, histories: dict[str, list[dict]]) -> None:
        """Record movements seen in the latest aircraft histories."""
        with self._lock:
            for icao24, states in histories.items():
                for state in states[-6:]:
                    hit = self._classify(state)
                    if hit:
                        kind, end = hit
                        self.events[(icao24, kind)] = {
                            "icao24": icao24, "callsign": state.get("callsign"), "kind": kind,
                            "end": end["end"], "runway": end["runway"],
                            "time": float(state.get("timePosition") or 0)}

    def summary(self, flights: list[dict], source: str, data_time: float,
                destination_of=lambda callsign: None) -> dict:
        metar = self.metar(source, data_time)
        with self._lock:
            recent = sorted((e for e in self.events.values() if data_time - EVENT_WINDOW_S <= e["time"] <= data_time + 60),
                            key=lambda e: e["time"], reverse=True)
            for key in [k for k, e in self.events.items() if data_time - e["time"] > 3 * 3600]:
                del self.events[key]
        landings = Counter(e["end"] for e in recent if e["kind"] == "landing")
        departures = Counter(e["end"] for e in recent if e["kind"] == "departure")
        if landings or departures:
            end = (landings or departures).most_common(1)[0][0]
            basis = (f"{landings[end]} landing{'s' if landings[end] != 1 else ''} observed in the last "
                     f"{EVENT_WINDOW_S // 60} min" if landings else
                     f"{departures[end]} departure{'s' if departures[end] != 1 else ''} observed in the last "
                     f"{EVENT_WINDOW_S // 60} min")
            in_use = {"end": end, "basis": basis, "derived": "observed movements"}
        elif metar and metar.get("windDirDeg") is not None and self.ends:
            best = min(self.ends, key=lambda e: angle_diff(e["heading"], metar["windDirDeg"]))
            in_use = {"end": best["end"], "basis": f"most into the reported surface wind {metar['windDirDeg']:03d}° / {metar['windKt']} kt; no movement observed yet",
                      "derived": "surface wind"}
        else:
            in_use = None

        # Arrivals still to come: low, descending, inside the arrival range, ETA from distance
        # and ground speed to the threshold of the runway in use. An estimate, and labelled so.
        upcoming = []
        target = next((e for e in self.ends if in_use and e["end"] == in_use["end"]), None)
        for f in flights:
            lat, lng = f.get("lat"), f.get("lng")
            if lat is None or f.get("onGround") or not target:
                continue
            alt, vs, kt = float(f.get("altitudeFt") or 0), float(f.get("verticalRateFpm") or 0), float(f.get("speedKt") or 0)
            dist = distance_nm(lat, lng, *target["threshold"])
            bound = destination_of(f.get("callsign")) == ICAO
            if dist > ARRIVAL_HORIZON_NM or kt < 80 or alt > 15_000:
                continue
            if not (bound or (vs < -300 and alt < 10_000)):
                continue
            if any(e["icao24"] == f.get("icao24") and e["kind"] == "landing" for e in recent):
                continue
            upcoming.append({"callsign": f.get("callsign"), "icao24": f.get("icao24"), "end": target["end"],
                             "distanceNm": round(dist, 1), "etaMinutes": round(dist / kt * 60, 1),
                             "basis": "destination VABB (route lookup)" if bound else "descending below 10,000 ft near VABB"})
        upcoming.sort(key=lambda u: u["etaMinutes"])
        return {
            "airport": ICAO,
            "dataTimeUtc": datetime.fromtimestamp(data_time, tz=timezone.utc).isoformat(),
            "runways": [{"end": e["end"], "runway": e["runway"], "headingDeg": round(e["heading"]),
                         "threshold": e["threshold"], "far": e["far"], "lengthFt": e["lengthFt"]} for e in self.ends],
            "runwaySource": "OurAirports runways.csv (public domain)",
            "inUse": in_use,
            "recentMovements": recent[:20],
            "upcomingArrivals": upcoming[:12],
            "metar": metar,
            "metarError": self.live.error if source == "live" else None,
            "notes": "Movements and runway in use are derived from the tracks, not from ATC. No ATIS is published "
                     "in a form we can read, so none is shown.",
        }


airport_service = AirportService()
