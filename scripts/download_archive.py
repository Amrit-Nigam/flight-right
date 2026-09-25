"""Bulk-download Mumbai traffic from the OpenSky historical archive (Trino).

Phase 2.3 established that the archive carries Indian traffic, and - the part that
matters - that it carries it BELOW 10,000 ft near VABB from **January 2025 onwards**
and not before. This script pulls that data down in the same shape as the twelve days
we collected by polling, so the existing pipeline can read it unchanged.

**It deliberately does NOT write into `ml_pipeline/data/raw/`.**
`preprocess_sequences.py` globs `raw/*.parquet` and concatenates whatever it finds. A
download dropped in there would silently change the dataset underneath every number this
project has published, with no record of when it happened. Files land in
`ml_pipeline/data/archive/` instead, and adopting them is a separate, deliberate step.

**Resolution: one sample every 10 seconds**, matching the poll interval of the recorded
sessions, so archive days and polled sessions are directly comparable. Full resolution is
about 2.0 million rows per day against 204,000 at 10 s, and nothing in the pipeline uses
sub-10-second detail.

**Sampling days rather than taking every day.** One day is already a third of the entire
current dataset, so a spread of days across many months buys seasonal variety - Mumbai's
monsoon changes the traffic - for far less disk and preprocessing time than consecutive
days would.

Run:  python scripts/download_archive.py --days-per-month 2
      python scripts/download_archive.py --from 2025-02 --to 2026-09 --days-per-month 3
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR = PROJECT_ROOT / "ml_pipeline" / "data" / "archive"

# The Mumbai demo box (CLAUDE.md Section 2), identical to what the pollers used.
LAT_MIN, LAT_MAX = 16.0, 23.5
LON_MIN, LON_MAX = 68.0, 77.5

SAMPLE_SECONDS = 10

# Phase 2.3: no low-altitude coverage near VABB before this. Earlier months hold only
# cruise traffic overflying the region, which is exactly the regime we are already good at.
FIRST_MONTH_WITH_LOW_COVERAGE = "2025-02"


def months_between(first: str, last: str) -> list[tuple[int, int]]:
    start_year, start_month = (int(x) for x in first.split("-"))
    end_year, end_month = (int(x) for x in last.split("-"))
    out = []
    index = start_year * 12 + start_month - 1
    while index <= end_year * 12 + end_month - 1:
        year, month = divmod(index, 12)
        out.append((year, month + 1))
        index += 1
    return out


def days_for_month(year: int, month: int, per_month: int) -> list[dt.datetime]:
    """Spread the sampled days through the month rather than clustering them."""
    if month == 12:
        length = 31
    else:
        length = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.date(year, month, 1)).days
    step = max(1, length // (per_month + 1))
    return [dt.datetime(year, month, min(length, step * (i + 1)), tzinfo=dt.timezone.utc)
            for i in range(per_month)]


def fetch_day(trino, day: dt.datetime) -> pd.DataFrame:
    """One calendar day, airborne, model-usable rows only, sampled every 10 s.

    Column names are mapped to the poller's schema here rather than downstream, so the
    archive files are drop-in comparable with the recorded sessions.
    """
    low = int(day.timestamp())
    high = low + 86400
    sql = f"""
        SELECT icao24,
               callsign,
               lastposupdate AS time_position,
               lastcontact   AS last_contact,
               lon           AS longitude,
               lat           AS latitude,
               baroaltitude  AS baro_altitude,
               geoaltitude   AS geo_altitude,
               onground      AS on_ground,
               velocity,
               heading       AS true_track,
               vertrate      AS vertical_rate,
               squawk,
               spi,
               time          AS state_time
        FROM state_vectors_data4
        WHERE hour >= {low} AND hour < {high}
          AND mod(time, {SAMPLE_SECONDS}) = 0
          AND lat BETWEEN {LAT_MIN} AND {LAT_MAX}
          AND lon BETWEEN {LON_MIN} AND {LON_MAX}
          AND onground = false
          AND lat IS NOT NULL AND lon IS NOT NULL
          AND baroaltitude IS NOT NULL AND velocity IS NOT NULL AND heading IS NOT NULL
          AND lastposupdate IS NOT NULL
    """
    frame = trino.query(sql)
    if frame.empty:
        return frame

    # The poller recorded when IT observed the aircraft; the archive's equivalent is the
    # state-vector time. Downstream replay groups frames on this, so it has to exist.
    frame["fetch_timestamp_utc"] = pd.to_datetime(frame["state_time"], unit="s", utc=True)
    frame["origin_country"] = None
    frame["sensors"] = None
    frame["position_source"] = 0
    frame["category"] = 0
    frame["callsign"] = frame["callsign"].fillna("").str.strip()
    frame["time_position"] = frame["time_position"].astype("int64")
    frame["last_contact"] = frame["last_contact"].fillna(frame["time_position"]).astype("int64")

    # A stale lastposupdate repeated across 10 s samples is the same fix twice. Keeping
    # both would tell the model an aircraft stood still.
    frame = frame.drop_duplicates(subset=["icao24", "time_position"], keep="first")
    return frame.sort_values(["icao24", "time_position"]).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="first", default=FIRST_MONTH_WITH_LOW_COVERAGE)
    parser.add_argument("--to", dest="last",
                        default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m"))
    parser.add_argument("--days-per-month", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true",
                        help="re-download days already on disk")
    args = parser.parse_args()

    logging.disable(logging.INFO)
    from pyopensky.trino import Trino
    trino = Trino()

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    targets = [day for year, month in months_between(args.first, args.last)
               for day in days_for_month(year, month, args.days_per_month)]
    now = dt.datetime.now(dt.timezone.utc)
    targets = [d for d in targets if d < now]

    print("=" * 88)
    print(f"ARCHIVE DOWNLOAD -- Mumbai box, airborne, every {SAMPLE_SECONDS}s")
    print(f"{args.first} to {args.last}, {args.days_per_month} day(s) per month "
          f"= {len(targets)} days")
    print(f"into {ARCHIVE_DIR}  (NOT data/raw -- adopting these is a separate step)")
    print("=" * 88)

    total_rows, downloaded, skipped, empty = 0, 0, 0, 0
    started = time.time()
    for day in targets:
        out = ARCHIVE_DIR / f"archive_{day:%Y%m%d}.parquet"
        if out.exists() and not args.overwrite:
            total_rows += len(pd.read_parquet(out, columns=["icao24"]))
            skipped += 1
            continue
        try:
            frame = fetch_day(trino, day)
        except Exception as failure:                                # noqa: BLE001
            print(f"  {day:%Y-%m-%d}  ERROR {type(failure).__name__}")
            continue
        if frame.empty:
            print(f"  {day:%Y-%m-%d}  no data")
            empty += 1
            continue
        frame.to_parquet(out, index=False)
        total_rows += len(frame)
        downloaded += 1
        print(f"  {day:%Y-%m-%d}  {len(frame):>8,} rows  "
              f"{frame['icao24'].nunique():>4} aircraft  "
              f"{out.stat().st_size/1e6:>6.1f} MB")

    elapsed = time.time() - started
    size = sum(p.stat().st_size for p in ARCHIVE_DIR.glob("archive_*.parquet"))
    print("-" * 88)
    print(f"downloaded {downloaded} | already present {skipped} | empty {empty}")
    print(f"total rows {total_rows:,}  on disk {size/1e6:.1f} MB  in {elapsed/60:.1f} min")
    print(f"\nfor scale: the existing polled dataset is 627,344 airborne states, so this "
          f"is {total_rows/627344:.1f}x it.")
    print("\nNothing downstream has changed. To use these, see docs/phase2_findings.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
