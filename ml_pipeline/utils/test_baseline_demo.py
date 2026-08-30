"""Read-only manual sanity check for the deterministic baseline modules."""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_pipeline.utils.cpa_conflict_detection import classify_conflict, compute_cpa
from ml_pipeline.utils.trajectory_baseline import predict_multiple_horizons


def state_from_row(row: pd.Series) -> dict[str, float]:
    """Map the raw OpenSky naming/units to the deterministic baseline schema."""
    return {
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        # OpenSky baro_altitude is specified in metres.
        "altitude_m": float(row["baro_altitude"]),
        "velocity_ms": float(row["velocity"]),
        "heading_deg": float(row["true_track"]),
        "vertical_rate_ms": 0.0 if pd.isna(row["vertical_rate"]) else float(row["vertical_rate"]),
    }


def main() -> None:
    raw_directory = PROJECT_ROOT / "ml_pipeline" / "data" / "raw"
    parquet_paths = [Path(path) for path in glob.glob(str(raw_directory / "*.parquet"))]
    if not parquet_paths:
        raise FileNotFoundError(f"No Parquet files found in {raw_directory}")
    latest_path = max(parquet_paths, key=lambda path: path.stat().st_mtime)
    raw = pd.read_parquet(latest_path)
    required = ["latitude", "longitude", "velocity", "true_track", "baro_altitude"]
    valid = raw.loc[(raw["on_ground"] == False) & raw[required].notna().all(axis=1)].head(2)  # noqa: E712
    if len(valid) < 2:
        raise ValueError("The latest file does not contain two valid airborne aircraft states.")

    aircraft_a, aircraft_b = state_from_row(valid.iloc[0]), state_from_row(valid.iloc[1])
    predictions_a = predict_multiple_horizons(aircraft_a)
    predictions_b = predict_multiple_horizons(aircraft_b)
    cpa = compute_cpa(predictions_a, predictions_b)
    label = classify_conflict(cpa)

    print(f"Loaded: {latest_path}")
    for name, row, predictions in (("A", valid.iloc[0], predictions_a), ("B", valid.iloc[1], predictions_b)):
        print(f"\nAircraft {name}: {row.get('callsign', row['icao24'])} ({row['icao24']})")
        print(f"  current: lat={row['latitude']:.5f}, lon={row['longitude']:.5f}, heading={row['true_track']:.1f} deg")
        for horizon, (lat, lon, altitude) in predictions.items():
            print(f"  {horizon:>5}: lat={lat:.5f}, lon={lon:.5f}, altitude={altitude:.1f} m")
    print("\nCPA result:")
    for horizon, values in cpa["per_horizon"].items():
        print(f"  {horizon:>5}: lateral={values['lateral_distance_nm']:.2f} NM, vertical={values['vertical_separation_ft']:.0f} ft")
    print(f"  CPA: {cpa['cpa_horizon_seconds']} s, {cpa['cpa_lateral_distance_nm']:.2f} NM, {cpa['cpa_vertical_separation_ft']:.0f} ft")
    print(f"  Label: conflict={label['is_conflict']}, severity={label['severity']}")


if __name__ == "__main__":
    main()
