"""Phase 2.6: how far back can adsb.lol per-aircraft trace files be fetched directly?

    python scripts/check_adsblol_history.py

Requests trace_full_<hex>.json under adsb.lol/globe_history/<YYYY/MM/DD>/ for two Indian
airframes across a spread of past days, records the HTTP status of each, and for one
served day per sample reports the span of the trace and how many points carry the
selected altitude (nav_altitude_mcp, trace element 8). Writes
ml_pipeline/reports/adsblol_history_<stamp>.json.

Uses certifi, not the Windows trust store: on this machine the default store is what made
atco2.org look "unreachable" in Phase 2.4.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import ssl
import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
AIRFRAMES = {"801742": "VT-IWQ", "80180e": "VT-NHB"}
CONTEXT = ssl.create_default_context(cafile=certifi.where())
HEADERS = {"User-Agent": "FlightRight-research/1.0 (academic project)", "Accept-Encoding": "gzip"}


def fetch(day: dt.date, hexid: str) -> tuple[int | str, dict | None]:
    url = f"https://adsb.lol/globe_history/{day:%Y/%m/%d}/traces/{hexid[-2:]}/trace_full_{hexid}.json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30,
                                    context=CONTEXT) as response:
            body = response.read()
            if body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            return response.status, json.loads(body)
    except Exception as error:  # noqa: BLE001 -- the status IS the measurement
        return getattr(error, "code", type(error).__name__), None


def summary(trace: dict) -> dict:
    points = trace["trace"]
    detail = [p for p in points if len(p) > 8 and isinstance(p[8], dict)]
    start = dt.datetime.fromtimestamp(trace["timestamp"] + points[0][0], dt.timezone.utc)
    end = dt.datetime.fromtimestamp(trace["timestamp"] + points[-1][0], dt.timezone.utc)
    return {"points": len(points), "first_utc": start.isoformat(), "last_utc": end.isoformat(),
            "detail_points": len(detail),
            "with_selected_altitude": sum("nav_altitude_mcp" in p[8] for p in detail)}


def main() -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    recent = [today - dt.timedelta(days=n) for n in range(1, 61)]
    older = [dt.date(y, m, d) for y, m in [(2024, 6), (2024, 12), (2025, 1), (2025, 2), (2025, 3),
                                           (2025, 6), (2025, 9), (2025, 12), (2026, 2), (2026, 4),
                                           (2026, 6), (2026, 7)] for d in (10, 11, 12)]
    report: dict = {"checked_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "airframes": {}}
    for hexid, registration in AIRFRAMES.items():
        statuses, samples = {}, {}
        for day in sorted(set(recent + older)):
            status, trace = fetch(day, hexid)
            statuses[day.isoformat()] = status
            if trace and day.strftime("%Y-%m") not in samples:
                samples[day.strftime("%Y-%m")] = {"day": day.isoformat(), **summary(trace)}
        served_recent = sorted(d.isoformat() for d in recent if statuses[d.isoformat()] == 200)
        report["airframes"][hexid] = {
            "registration": registration, "statuses": statuses, "samples": samples,
            "recent_window_first_served": served_recent[0] if served_recent else None,
            "recent_days_served": f"{len(served_recent)} of {len(recent)}",
            "older_days_served": f"{sum(statuses[d.isoformat()] == 200 for d in older)} of {len(older)}"}
        print(f"{registration}: recent {report['airframes'][hexid]['recent_days_served']} "
              f"(first {report['airframes'][hexid]['recent_window_first_served']}), older "
              f"{report['airframes'][hexid]['older_days_served']}")
    out = ROOT / "ml_pipeline/reports" / f"adsblol_history_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
