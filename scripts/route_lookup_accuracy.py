"""Plan 9.2: how often do free callsign-to-route lookups agree with where Indian flights went?

    python scripts/route_lookup_accuracy.py

The plan notes there is no published figure for India (benchmarked elsewhere at roughly
60% in Southeast Asia and 13-27% in the US). This measures it on our own flights.

  TRUTH   OpenSky's flights table (Trino, `flights_data4`): per airframe per day, the
          estimated departure and arrival airport. It is OpenSky's own estimate, so it is
          cross-checked here against the VABB landings detected by scripts/derive_runways.py
          where those exist.
  LOOKUPS adsbdb  https://api.adsbdb.com/v0/callsign/<callsign>
          hexdb   https://hexdb.io/callsign-route?callsign=<callsign>
          Both answer "which route does this callsign normally fly", which is exactly what a
          system without flight-plan data would use as a stand-in destination.

Politeness: every lookup is cached to ml_pipeline/data/routes/ and never repeated, at most
two requests a second. Writes ml_pipeline/reports/route_lookup_<stamp>.json.
"""
from __future__ import annotations

import glob
import json
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import certifi
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "ml_pipeline/data/routes"
CONTEXT = ssl.create_default_context(cafile=certifi.where())
HEADERS = {"User-Agent": "FlightRight-research/1.0 (academic project; cached, 2 req/s)"}
_last = [0.0]


def polite_get(url: str) -> tuple[int, bytes]:
    wait = 0.5 - (time.monotonic() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30, context=CONTEXT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read() if hasattr(error, "read") else b""
    except Exception:  # noqa: BLE001
        return 0, b""


def lookup(service: str, callsign: str) -> dict:
    path = CACHE / service / f"{callsign}.json"
    if path.exists():
        return json.loads(path.read_text())
    path.parent.mkdir(parents=True, exist_ok=True)
    if service == "adsbdb":
        status, body = polite_get(f"https://api.adsbdb.com/v0/callsign/{urllib.parse.quote(callsign)}")
        route = {}
        try:
            fr = json.loads(body)["response"]["flightroute"]
            route = {"origin": fr["origin"]["icao_code"], "destination": fr["destination"]["icao_code"]}
        except Exception:  # noqa: BLE001 -- "unknown callsign" is an answer, recorded as such
            pass
    else:
        status, body = polite_get(f"https://hexdb.io/callsign-route?callsign={urllib.parse.quote(callsign)}")
        text = body.decode("utf-8", "replace").strip()
        route = {}
        if status == 200 and "-" in text and "n/a" not in text.lower():
            parts = text.split("-")
            route = {"origin": parts[0].strip().upper(), "destination": parts[-1].strip().upper()}
    record = {"status": status, **route}
    if status in (200, 404):
        path.write_text(json.dumps(record))
    return record


def flights() -> pd.DataFrame:
    frames = [pd.read_parquet(f, columns=["icao24", "callsign", "time_position"])
              for f in sorted(glob.glob(str(ROOT / "ml_pipeline/data/raw/*.parquet")))]
    d = pd.concat(frames).dropna()
    d["callsign"] = d["callsign"].str.strip()
    d = d[d["callsign"].str.len() > 2]
    d["day"] = pd.to_datetime(d["time_position"], unit="s", utc=True).dt.floor("D")
    return d.groupby(["icao24", "callsign", "day"], as_index=False)["time_position"].agg(["min", "max"])


def truth(ours: pd.DataFrame) -> pd.DataFrame:
    from pyopensky.trino import Trino
    trino, parts = Trino(), []
    for day, group in ours.groupby("day"):
        hexes = ",".join(f"'{h}'" for h in sorted(group["icao24"].unique()))
        start = int(day.timestamp())
        sql = (f"SELECT icao24, callsign, firstseen, lastseen, estdepartureairport, estarrivalairport "
               f"FROM flights_data4 WHERE day = {start} AND icao24 IN ({hexes})")
        part = trino.query(sql)
        if part is not None and len(part):
            parts.append(part)
        print(f"  truth {day:%Y-%m-%d}: {0 if part is None else len(part)} flights", flush=True)
    t = pd.concat(parts, ignore_index=True)
    t["callsign"] = t["callsign"].fillna("").str.strip()
    return t


def main() -> None:
    ours = flights()
    print(f"{len(ours):,} callsign-days in our sessions, {ours['callsign'].nunique():,} callsigns")
    t = truth(ours)
    t["firstseen"] = pd.to_numeric(pd.to_datetime(t["firstseen"], utc=True).astype("int64") // 10**9 if not pd.api.types.is_numeric_dtype(t["firstseen"]) else t["firstseen"])
    t["lastseen"] = pd.to_numeric(pd.to_datetime(t["lastseen"], utc=True).astype("int64") // 10**9 if not pd.api.types.is_numeric_dtype(t["lastseen"]) else t["lastseen"])
    # Join each of our callsign-days to the OpenSky flight that contains our observations.
    joined = ours.merge(t, on=["icao24", "callsign"], how="inner")
    joined = joined[(joined["firstseen"] <= joined["max"]) & (joined["lastseen"] >= joined["min"])]
    joined = joined.dropna(subset=["estdepartureairport", "estarrivalairport"])
    joined = joined.drop_duplicates(["icao24", "callsign", "day"])
    print(f"{len(joined):,} flights with both a truth departure and arrival")

    rows = []
    for record in joined.itertuples(index=False):
        row = {"callsign": record.callsign, "truth_origin": record.estdepartureairport,
               "truth_destination": record.estarrivalairport}
        for service in ("adsbdb", "hexdb"):
            found = lookup(service, record.callsign)
            row[f"{service}_origin"], row[f"{service}_destination"] = found.get("origin"), found.get("destination")
        rows.append(row)
    r = pd.DataFrame(rows)

    # Cross-check the truth itself against our own detected VABB landings, where we have them.
    landings_path = ROOT / "ml_pipeline/data/processed/runway_landings.parquet"
    crosscheck = None
    if landings_path.exists():
        landed = set(pd.read_parquet(landings_path)["callsign"].str.strip())
        sub = r[r["callsign"].isin(landed)]
        crosscheck = {"flights_we_saw_land_at_vabb": int(len(sub)),
                      "of_which_opensky_says_arrival_vabb": int((sub["truth_destination"] == "VABB").sum())}

    result = {"checked_utc": datetime.now(timezone.utc).isoformat(), "flights": int(len(r)),
              "truth": "OpenSky flights_data4 estdepartureairport / estarrivalairport", "truth_crosscheck": crosscheck}
    for service in ("adsbdb", "hexdb"):
        known = r[f"{service}_origin"].notna()
        both = known & (r[f"{service}_origin"] == r["truth_origin"]) & (r[f"{service}_destination"] == r["truth_destination"])
        dest = known & (r[f"{service}_destination"] == r["truth_destination"])
        vabb = r["truth_destination"].eq("VABB") | r["truth_origin"].eq("VABB")
        result[service] = {
            "answered": int(known.sum()), "answered_share": float(known.mean()),
            "route_exactly_right_of_all": float(both.mean()),
            "route_exactly_right_of_answered": float(both[known].mean()) if known.any() else None,
            "destination_right_of_all": float(dest.mean()),
            "mumbai_flights": int(vabb.sum()),
            "mumbai_route_exactly_right": float(both[vabb].mean()) if vabb.any() else None,
        }
    out = ROOT / "ml_pipeline/reports" / f"route_lookup_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
