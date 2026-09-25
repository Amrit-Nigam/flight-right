"""Plan 9.0: fetch adsb.lol per-aircraft day traces for the aircraft in our own sessions.

    python scripts/fetch_adsblol_traces.py            # every aircraft-day in data/raw
    python scripts/fetch_adsblol_traces.py --limit 50 # a sample

WHY NOW. adsb.lol serves per-aircraft day traces directly for a rolling ~six weeks (Phase
2.6, measured 24 Sep 2026: every day from 13 Aug onward). Our 35 sessions run 24 Aug - 5 Sep
2026, so the selected altitude (`nav_altitude_mcp`) and the aircraft's own wind reports for
exactly the aircraft and days our models train and test on are still fetchable -- and the
earliest of them rolls off around 5 Oct 2026. After that, backfill needs the bulk GitHub
releases.

POLITENESS. adsb.lol publishes no rate limit. This fetches at most two files a second on one
connection, with a user agent naming the project, and never re-fetches a file already on
disk (a 404 is remembered too), so a rerun resumes rather than repeats.

LICENCE. adsb.lol historical data is ODbL 1.0: attribution, and share-alike for any derived
database that is distributed. The files stay local under ml_pipeline/data/adsblol/
(gitignored); anything derived that is published must carry the attribution and licence.

Writes ml_pipeline/data/adsblol/traces/<YYYY-MM-DD>/<icao24>.json.gz and a summary
ml_pipeline/reports/adsblol_fetch_<stamp>.json.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import certifi
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ml_pipeline/data/adsblol/traces"
CONTEXT = ssl.create_default_context(cafile=certifi.where())
HEADERS = {"User-Agent": "FlightRight-research/1.0 (academic project; polite fetch, 2 req/s)",
           "Accept-Encoding": "gzip"}
MIN_INTERVAL_S = 0.5


def aircraft_days() -> pd.DataFrame:
    frames = [pd.read_parquet(f, columns=["icao24", "time_position", "on_ground"])
              for f in sorted(glob.glob(str(ROOT / "ml_pipeline/data/raw/*.parquet")))]
    d = pd.concat(frames)
    d = d[d["time_position"].notna() & (d["on_ground"] == False)]  # noqa: E712
    d["date"] = pd.to_datetime(d["time_position"], unit="s", utc=True).dt.strftime("%Y-%m-%d")
    return d[["date", "icao24"]].drop_duplicates().sort_values(["date", "icao24"]).reset_index(drop=True)


def fetch(date: str, hexid: str) -> str:
    target = OUT / date / f"{hexid}.json.gz"
    missing = target.with_suffix(".missing")
    if target.exists():
        return "cached"
    if missing.exists():
        return "cached-404"
    url = f"https://adsb.lol/globe_history/{date.replace('-', '/')}/traces/{hexid[-2:]}/trace_full_{hexid}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30, context=CONTEXT) as r:
            body = r.read()
        if body[:2] != b"\x1f\x8b":
            body = gzip.compress(body)
        json.loads(gzip.decompress(body))       # refuse to keep anything that is not a trace
        target.write_bytes(body)
        return "fetched"
    except urllib.error.HTTPError as error:
        if error.code == 404:
            missing.write_text("404")
            return "404"
        return f"http-{error.code}"
    except Exception as error:  # noqa: BLE001 -- recorded, retried on the next run
        return type(error).__name__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    todo = aircraft_days()
    if args.limit:
        todo = todo.sample(args.limit, random_state=0)
    print(f"{len(todo):,} aircraft-days to check ({todo['icao24'].nunique():,} aircraft, "
          f"{todo['date'].nunique()} dates)")
    counts: dict[str, int] = {}
    last = 0.0
    for n, (date, hexid) in enumerate(todo.itertuples(index=False), 1):
        wait = MIN_INTERVAL_S - (time.monotonic() - last)
        if wait > 0 and not (OUT / date / f"{hexid}.json.gz").exists():
            time.sleep(wait)
        last = time.monotonic()
        status = fetch(date, hexid)
        counts[status] = counts.get(status, 0) + 1
        if n % 250 == 0:
            print(f"  {n:,}/{len(todo):,} {counts}", flush=True)
    summary = {"checked_utc": datetime.now(timezone.utc).isoformat(), "aircraft_days": len(todo),
               "by_status": counts, "by_date": todo.groupby("date").size().to_dict()}
    out = ROOT / "ml_pipeline/reports" / f"adsblol_fetch_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"done {counts} -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
