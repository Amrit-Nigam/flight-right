"""Maintainer: prepare a redistributable replay; never copy OpenSky recordings/secrets.

Uses the locally retained adsb.lol daily traces (ODbL), not invented flight paths.
Run with the project venv; users running the demo do not run this script.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-04"
START = datetime(2026, 9, 4, 20, 45, tzinfo=timezone.utc).timestamp()
END = START + 90 * 60
SPEECH = "checkpoints/voice_20261110/ct2/local__uniform_soup3__int8_float16"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def number(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def main():
    output = ROOT / "demo"
    rows, metadata, sources = [], [], []
    for path in sorted((ROOT / "ml_pipeline/data/adsblol/traces" / DAY).glob("*.json.gz")):
        record = json.loads(gzip.decompress(path.read_bytes()))
        fields = {}
        used = False
        for point in record.get("trace", []):
            if len(point) > 8 and isinstance(point[8], dict):
                fields.update(point[8])
            at = float(record["timestamp"]) + float(point[0])
            if not START <= at <= END or len(point) < 8:
                continue
            lat, lon, altitude, speed, track, rate = point[1], point[2], point[3], point[4], point[5], point[7]
            if not all(number(x) for x in (lat, lon, altitude, speed, track)):
                continue  # ground and incomplete states are not airborne measurements
            if not (16 <= lat <= 23.5 and 68 <= lon <= 77.5):
                continue
            geo = point[10] if len(point) > 10 and number(point[10]) else None
            rows.append({"icao24": record["icao"], "callsign": str(fields.get("flight") or record["icao"]).strip(),
                         "latitude": lat, "longitude": lon, "baro_altitude": altitude / 3.28084,
                         "geo_altitude": geo / 3.28084 if geo is not None else None,
                         "velocity": speed / 1.94384, "true_track": track,
                         "vertical_rate": (rate if number(rate) else 0) / 196.8504,
                         "on_ground": False, "origin_country": "Unknown",
                         "time_position": at, "fetch_timestamp_utc": pd.Timestamp(int(at // 10) * 10, unit="s", tz="UTC")})
            used = True
        if used:
            metadata.append({"icao24": record["icao"], "registration": record.get("r"),
                             "type": record.get("t"), "description": record.get("desc")})
            sources.append({"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)})
    if not rows:
        raise RuntimeError("No saved adsb.lol traces for the demo interval")
    frame = pd.DataFrame(rows).sort_values("time_position").drop_duplicates(["fetch_timestamp_utc", "icao24"], keep="last")
    raw = output / "replay"
    raw.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(raw / "adsblol_20260904_204500.parquet", index=False)
    context = output / "context"
    context.mkdir(exist_ok=True)
    pd.DataFrame(metadata).to_parquet(context / "aircraft_info.parquet", index=False)
    intent = pd.read_parquet(ROOT / "ml_pipeline/data/adsblol/intent.parquet")
    intent = intent[intent.icao24.isin(frame.icao24.unique()) & intent.time.between(START - 300, END)]
    intent.to_parquet(context / "intent.parquet", index=False)
    # Public reference data and cached route facts. Never copy a whole data/cache folder.
    paths = []
    for name in ("ourairports_airports.csv", "ourairports_runways.csv"):
        paths.append("ml_pipeline/data/routes/" + name)
    paths.append("ml_pipeline/data/weather/metar_VABB.csv")
    routes = {}
    for callsign in sorted(frame.callsign.unique()):
        path = ROOT / "ml_pipeline/data/routes/adsbdb" / f"{callsign}.json"
        if path.is_file():
            routes[callsign] = json.loads(path.read_text())
    (context / "routes.json").write_text(json.dumps({"schema": 1, "provider": "adsbdb", "routes": routes}, indent=2) + "\n", encoding="utf-8")
    voice = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlightRight/voice"
    for name in ("faa_7340_chap3_sec3.html", "openflights_airlines.dat"):
        target = output / "voice" / name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(voice / name, target)
    # Exclude research-only ATCO2 recordings; only the three generated practice calls.
    clips = output / "clips"
    clips.mkdir(exist_ok=True)
    entries = []
    for entry in json.loads((voice / "demo_clips/index.json").read_text(encoding="utf-8")):
        if not entry.get("synthetic"):
            continue
        entry["transcripts"] = {}  # no stale transcripts or machine-specific paths
        shutil.copyfile(voice / "demo_clips" / f"{entry['id']}.wav", clips / f"{entry['id']}.wav")
        entries.append(entry)
    (clips / "index.json").write_text(json.dumps(entries, indent=2), encoding="utf-8")
    provenance = {"provider": "adsb.lol", "license": "ODbL-1.0",
                  "source_url": "https://github.com/adsblol/globe_history_2026",
                  "start_utc": datetime.fromtimestamp(START, timezone.utc).isoformat(),
                  "end_utc": datetime.fromtimestamp(END, timezone.utc).isoformat(),
                  "rows": len(frame), "aircraft": int(frame.icao24.nunique()),
                  "construction": "Latest measured report per aircraft per 10-second bucket; unit conversion; no invented/interpolated positions.",
                  "limitations": "Limited to locally retained aircraft traces, not an exhaustive airport recording. Not an accuracy evaluation.",
                  "sources": sources}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    paths += ["server/app/ml/saved_models/" + name for name in
              ("trajectory_residual.pt", "trajectory_multipath.pkl", "xgboost_conflict.json", "xgboost_conflict_model_card.json")]
    paths += [SPEECH + "/" + name for name in
              ("model.bin", "config.json", "tokenizer.json", "vocabulary.json", "preprocessor_config.json", "README.md")]
    paths += [p.relative_to(ROOT).as_posix() for folder in (raw, context, clips, output / "voice")
              for p in folder.rglob("*") if p.is_file()]
    paths.append("demo/provenance.json")
    manifest = {"schema": 1, "speech_runtime": SPEECH, "replay_directory": "demo/replay",
                "files": [{"path": name, "bytes": (ROOT / name).stat().st_size, "sha256": sha(ROOT / name)}
                          for name in sorted(set(paths))]}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(frame)} reports from {frame.icao24.nunique()} aircraft; {len(manifest['files'])} pinned files")


if __name__ == "__main__":
    main()
