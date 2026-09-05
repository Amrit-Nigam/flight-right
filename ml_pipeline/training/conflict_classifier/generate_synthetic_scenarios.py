"""Build CPA-labelled aircraft-pair examples from real OpenSky aircraft states.

The pair geometry is synthetic, but aircraft A's altitude, airspeed, and vertical
rate always originate in the raw feed.  Labels are deliberately produced by the
existing deterministic CPA utilities, rather than by the generation intent.
"""

from __future__ import annotations

import glob
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd


# Change these values to regenerate a differently sized/balanced data set.
N_SCENARIOS = 2_000
CONFLICT_RATIO = 0.30
RANDOM_SEED = 42

EARTH_RADIUS_M = 6_371_000.0
NM_TO_M = 1_852.0
M_TO_FT = 3.28084
SECONDS_TO_PROJECT = 10 * 60

# One seeded generator is used for every synthetic choice in this module.
RNG = np.random.default_rng(RANDOM_SEED)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# These are intentionally reused as the single source of truth for prediction
# and labels.  Do not duplicate their deterministic CPA logic here.
from ml_pipeline.utils.cpa_conflict_detection import compute_cpa_from_states, classify_conflict


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles."""
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    d_lat = lat2_rad - lat1_rad
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2) ** 2
    return (2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))) / NM_TO_M


def _destination(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """Return the point reached after travelling a distance on a spherical Earth."""
    angular_distance = distance_m / EARTH_RADIUS_M
    bearing = math.radians(bearing_deg)
    lat1, lon1 = math.radians(lat), math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), ((math.degrees(lon2) + 540) % 360) - 180


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from the first coordinate to the second, in [0, 360)."""
    d_lon = math.radians(lon2 - lon1)
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    y = math.sin(d_lon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lon)
    return math.degrees(math.atan2(y, x)) % 360


def _state_from_seed(seed_row: Mapping[str, Any]) -> dict[str, float]:
    """Convert an OpenSky raw row to the state schema required by the predictor."""
    return {
        "latitude": float(seed_row["latitude"]),
        "longitude": float(seed_row["longitude"]),
        # OpenSky baro_altitude is already metres; retain the real altitude.
        "altitude_m": float(seed_row["baro_altitude"]),
        "velocity_ms": float(seed_row["velocity"]),
        "heading_deg": float(seed_row["true_track"]) % 360,
        # This field can be null in some feeds, so use level flight only when
        # absent; valid real vertical rates are left unchanged.
        "vertical_rate_ms": 0.0 if pd.isna(seed_row.get("vertical_rate")) else float(seed_row["vertical_rate"]),
    }


def generate_scenario(seed_row: Mapping[str, Any], force_conflict: bool) -> tuple[dict[str, float], dict[str, float]]:
    """Create an aircraft pair, seeded by a real airborne aircraft observation."""
    aircraft_a = _state_from_seed(seed_row)
    aircraft_b = dict(aircraft_a)

    # Start B 2--15 NM from A at a random bearing; this is the initial geometry.
    offset_nm = RNG.uniform(2.0, 15.0)
    offset_bearing = RNG.uniform(0.0, 360.0)
    aircraft_b["latitude"], aircraft_b["longitude"] = _destination(
        aircraft_a["latitude"], aircraft_a["longitude"], offset_bearing, offset_nm * NM_TO_M
    )

    # Keep B operationally plausible by perturbing A's genuine altitude/speed.
    altitude_limit_ft = 1_500.0 if force_conflict else 2_000.0
    aircraft_b["altitude_m"] += RNG.uniform(-altitude_limit_ft, altitude_limit_ft) / M_TO_FT
    aircraft_b["velocity_ms"] *= RNG.uniform(0.90, 1.10)

    if force_conflict:
        # Project A along its *real* track for ten minutes, then point B at that
        # future location.  A heading to this point closes the lateral gap,
        # while the tight altitude bias above improves (but never guarantees)
        # vertical proximity.  CPA remains the authority for the final label.
        future_a_lat, future_a_lon = _destination(
            aircraft_a["latitude"], aircraft_a["longitude"], aircraft_a["heading_deg"],
            aircraft_a["velocity_ms"] * SECONDS_TO_PROJECT,
        )
        aircraft_b["heading_deg"] = _bearing_deg(
            aircraft_b["latitude"], aircraft_b["longitude"], future_a_lat, future_a_lon
        )
    else:
        # Natural negatives: do not force an outbound track.  Coincidental
        # conflicts are intentionally retained and will receive CPA labels.
        aircraft_b["heading_deg"] = RNG.uniform(0.0, 360.0)

    return aircraft_a, aircraft_b


def load_seed_pool(raw_directory: Path | None = None) -> pd.DataFrame:
    """Load every raw parquet file and retain valid airborne states only."""
    raw_directory = raw_directory or PROJECT_ROOT / "ml_pipeline" / "data" / "raw"
    parquet_paths = sorted(glob.glob(str(raw_directory / "*.parquet")))
    if not parquet_paths:
        raise FileNotFoundError(f"No Parquet files found in {raw_directory}")

    seed_pool = pd.concat((pd.read_parquet(path) for path in parquet_paths), ignore_index=True)
    required = ["on_ground", "latitude", "longitude", "velocity", "true_track", "baro_altitude"]
    missing = sorted(set(required).difference(seed_pool.columns))
    if missing:
        raise ValueError(f"Raw data is missing required columns: {missing}")

    seed_pool = seed_pool.loc[(seed_pool["on_ground"] == False) & seed_pool[required[1:]].notna().all(axis=1)].copy()  # noqa: E712
    if seed_pool.empty:
        raise ValueError("No valid airborne rows remain after seed-pool filtering.")
    return seed_pool.reset_index(drop=True)


def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
    """Accept dict-like results while making unexpected utility APIs explicit."""
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "_asdict"):
        return value._asdict()
    raise TypeError(f"{name} must return a mapping; got {type(value).__name__}.")


def _first_value(values: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in values:
            return values[name]
    raise KeyError(f"Expected one of {names} in CPA/classification result; got {list(values)}")


def _relative_motion_features(aircraft_a: Mapping[str, float], aircraft_b: Mapping[str, float]) -> tuple[float, float, float]:
    """Return relative speed, folded heading difference, and radial closing speed."""
    heading_a, heading_b = math.radians(aircraft_a["heading_deg"]), math.radians(aircraft_b["heading_deg"])
    # East/North velocity components; aviation headings are clockwise from north.
    va = np.array([aircraft_a["velocity_ms"] * math.sin(heading_a), aircraft_a["velocity_ms"] * math.cos(heading_a)])
    vb = np.array([aircraft_b["velocity_ms"] * math.sin(heading_b), aircraft_b["velocity_ms"] * math.cos(heading_b)])
    relative_speed = float(np.linalg.norm(vb - va))
    heading_difference = abs((aircraft_b["heading_deg"] - aircraft_a["heading_deg"] + 180) % 360 - 180)
    # Local east/north displacement from A to B.  Positive closing means the
    # relative velocity points back toward A, reducing their present range.
    mean_lat = math.radians((aircraft_a["latitude"] + aircraft_b["latitude"]) / 2)
    displacement = np.array([
        math.radians(aircraft_b["longitude"] - aircraft_a["longitude"]) * EARTH_RADIUS_M * math.cos(mean_lat),
        math.radians(aircraft_b["latitude"] - aircraft_a["latitude"]) * EARTH_RADIUS_M,
    ])
    closing_speed = float(-np.dot(vb - va, displacement / np.linalg.norm(displacement)))
    return relative_speed, heading_difference, closing_speed


def build_labeled_dataset(seed_pool_df: pd.DataFrame, n_scenarios: int = N_SCENARIOS, conflict_ratio: float = CONFLICT_RATIO) -> pd.DataFrame:
    """Generate intended mixes, then assign authoritative labels through CPA."""
    if n_scenarios <= 0 or not 0 <= conflict_ratio <= 1:
        raise ValueError("n_scenarios must be positive and conflict_ratio must be between 0 and 1.")

    n_intended_conflicts = int(round(n_scenarios * conflict_ratio))
    intents = np.array([True] * n_intended_conflicts + [False] * (n_scenarios - n_intended_conflicts))
    RNG.shuffle(intents)
    seed_indices = RNG.integers(0, len(seed_pool_df), size=n_scenarios)
    rows: list[dict[str, Any]] = []

    for seed_index, force_conflict in zip(seed_indices, intents):
        aircraft_a, aircraft_b = generate_scenario(seed_pool_df.iloc[int(seed_index)], bool(force_conflict))
        # Labels come from the dense CPA grid, not the four named horizons. A pair
        # whose true CPA falls at t = 240 s used to be labelled from its separation at
        # 180 s and 300 s, so genuine conflicts were labelled negative and the
        # classifier was trained to miss exactly the encounters it exists to catch.
        cpa = _as_mapping(compute_cpa_from_states(aircraft_a, aircraft_b), "compute_cpa_from_states")
        classification = _as_mapping(classify_conflict(cpa), "classify_conflict")
        relative_speed, relative_heading, closing_speed = _relative_motion_features(aircraft_a, aircraft_b)

        rows.append({
            "relative_distance_nm": _haversine_nm(aircraft_a["latitude"], aircraft_a["longitude"], aircraft_b["latitude"], aircraft_b["longitude"]),
            "relative_altitude_ft": abs(aircraft_b["altitude_m"] - aircraft_a["altitude_m"]) * M_TO_FT,
            "relative_speed_ms": relative_speed,
            "relative_heading_deg": relative_heading,
            "closing_speed_ms": closing_speed,
            "time_to_cpa_seconds": _first_value(cpa, "cpa_horizon_seconds", "time_to_cpa_seconds", "time_to_cpa", "cpa_time_seconds"),
            "predicted_min_lateral_separation_nm": _first_value(cpa, "cpa_lateral_distance_nm", "min_lateral_separation_nm", "lateral_separation_nm", "min_lateral_nm"),
            "predicted_min_vertical_separation_ft": _first_value(cpa, "cpa_vertical_separation_ft", "min_vertical_separation_ft", "vertical_separation_ft", "min_vertical_ft"),
            "vertical_convergence_rate_ms": abs(aircraft_b["vertical_rate_ms"] - aircraft_a["vertical_rate_ms"]),
            "is_conflict": int(_first_value(classification, "is_conflict")),
            "severity": _first_value(classification, "severity"),
        })

    return pd.DataFrame(rows)


def main() -> None:
    seed_pool = load_seed_pool()
    dataset = build_labeled_dataset(seed_pool)
    output_directory = PROJECT_ROOT / "ml_pipeline" / "data" / "synthetic"
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_directory / f"conflict_scenarios_{timestamp}.parquet"
    dataset.to_parquet(output_path, index=False)

    class_balance = dataset["is_conflict"].value_counts().sort_index()
    severity_balance = dataset["severity"].value_counts()
    print(f"Total scenarios generated: {len(dataset)}")
    print("is_conflict class balance:\n" + class_balance.to_string())
    print("severity class balance:\n" + severity_balance.to_string())
    print(f"Output file path: {output_path}")


if __name__ == "__main__":
    main()
