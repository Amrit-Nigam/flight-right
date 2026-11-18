"""Cache Mumbai's archived METARs for every recorded session, so replay shows real weather offline.

    python scripts/fetch_metar_archive.py

Reads the date range of ml_pipeline/data/raw/*.parquet (fetch_timestamp_utc) and downloads VABB's
METARs for those UTC days from the Iowa Environmental Mesonet ASOS archive
(https://mesonet.agron.iastate.edu/request/download.phtml) into ml_pipeline/data/weather/metar_VABB.csv.
Run once; the backend reads the cache (server/app/services/airport_service.py).
"""
from __future__ import annotations

import sys
from datetime import timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.app.services.airport_service import MetarArchive  # noqa: E402


def main() -> None:
    stamps = []
    for path in sorted((ROOT / "ml_pipeline/data/raw").glob("*.parquet")):
        column = pd.read_parquet(path, columns=["fetch_timestamp_utc"])["fetch_timestamp_utc"]
        stamps += [column.min(), column.max()]
    if not stamps:
        raise SystemExit("no recorded sessions in ml_pipeline/data/raw")
    first, last = min(stamps).to_pydatetime(), max(stamps).to_pydatetime()
    archive = MetarArchive()
    added = archive.fetch_days(first.astimezone(timezone.utc), last.astimezone(timezone.utc))
    rows = archive._load()
    print(f"sessions span {first:%Y-%m-%d %H:%M} .. {last:%Y-%m-%d %H:%M} UTC; "
          f"{added} reports downloaded; cache holds {len(rows)} -> {archive.path}")


if __name__ == "__main__":
    main()
