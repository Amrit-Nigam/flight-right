"""Fetch one OpenSky state-vector snapshot for the Mumbai FIR and save it."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network/"
    "protocol/openid-connect/token"
)
STATES_URL = "https://opensky-network.org/api/states/all"
MUMBAI_FIR_BOUNDS = {"lamin": 16.0, "lomin": 68.0, "lamax": 23.5, "lomax": 77.5, "extended": 1}
STATE_COLUMNS = [
    "icao24",
    "callsign",
    "origin_country",
    "time_position",
    "last_contact",
    "longitude",
    "latitude",
    "baro_altitude",
    "on_ground",
    "velocity",
    "true_track",
    "vertical_rate",
    "sensors",
    "geo_altitude",
    "squawk",
    "spi",
    "position_source",
    "category",
]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "ml_pipeline" / "data" / "raw"


def exit_with_error(message: str) -> None:
    """Print an actionable message and end this one-shot script with failure."""
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    # Load local credentials from the project-root .env file.
    load_dotenv(PROJECT_ROOT / ".env")
    client_id = os.environ.get("OPENSKY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("OPENSKY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        exit_with_error(
            "Missing OPENSKY_CLIENT_ID or OPENSKY_CLIENT_SECRET in the project-root .env file."
        )

    # Exchange client credentials for a short-lived OAuth2 bearer token.
    try:
        token_response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
    except requests.RequestException as error:
        exit_with_error(f"OpenSky token request failed: {error}")
    except ValueError:
        exit_with_error("OpenSky token request returned invalid JSON.")

    if not access_token:
        exit_with_error("OpenSky token request succeeded but no access_token was returned.")

    # Fetch one state-vector snapshot within the Mumbai FIR bounding box.
    try:
        states_response = requests.get(
            STATES_URL,
            params=MUMBAI_FIR_BOUNDS,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except requests.RequestException as error:
        exit_with_error(f"OpenSky states request failed: {error}")

    if states_response.status_code == 401:
        exit_with_error("OpenSky states request was unauthorized (401). Obtain a new token or check credentials.")
    if states_response.status_code == 429:
        exit_with_error("OpenSky states request was rate limited (429). Check API credits and try later.")
    if states_response.status_code != 200:
        exit_with_error(
            f"OpenSky states request failed with HTTP {states_response.status_code}: "
            f"{states_response.text[:300]}"
        )

    try:
        response_data = states_response.json()
    except ValueError:
        exit_with_error("OpenSky states request returned invalid JSON.")

    # Convert OpenSky's positional state arrays into named DataFrame columns.
    states = response_data.get("states") or []
    dataframe = pd.DataFrame(states, columns=STATE_COLUMNS)
    dataframe["callsign"] = dataframe["callsign"].map(
        lambda value: value.strip() if isinstance(value, str) else value
    )
    fetch_timestamp = datetime.now(timezone.utc)
    dataframe["fetch_timestamp_utc"] = fetch_timestamp

    # Save this one fetch under a unique UTC timestamped filename.
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RAW_DATA_DIR / f"states_{fetch_timestamp.strftime('%Y%m%d_%H%M%S')}.parquet"
    dataframe.to_parquet(output_path, engine="pyarrow", index=False)

    # Report the result, including the optional rate-limit usage indicator.
    rate_limit_remaining = states_response.headers.get("X-Rate-Limit-Remaining", "not provided")
    print(f"Aircraft returned: {len(dataframe)}")
    print(f"Output file: {output_path}")
    print(f"X-Rate-Limit-Remaining: {rate_limit_remaining}")
    if dataframe.empty:
        print("No aircraft were currently returned for the Mumbai FIR bounding box; saved empty Parquet file.")


if __name__ == "__main__":
    main()
