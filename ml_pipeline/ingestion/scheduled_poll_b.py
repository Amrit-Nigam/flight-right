"""Poll OpenSky state vectors for one bounded session using account B."""

from __future__ import annotations

import os
import sys
import time
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

# This script is dedicated to API account B. Only the credential variables
# and the output label differ from the original scheduled_poll.py.
ACCOUNT_LABEL = "b"
CLIENT_ID_VARIABLE = "OPENSKY_CLIENT_ID_B"
CLIENT_SECRET_VARIABLE = "OPENSKY_CLIENT_SECRET_B"

# Session controls: adjust these constants before starting a collection session.
POLL_INTERVAL_SECONDS = 10
SESSION_DURATION_MINUTES = 90
CREDIT_SAFETY_THRESHOLD = 200
TOKEN_REFRESH_BUFFER_SECONDS = 60
# Snapshot progress this often (60 polls = ~10 min) so an abrupt kill loses
# minutes rather than the whole session.
CHECKPOINT_EVERY_POLLS = 60

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "ml_pipeline" / "data" / "raw"


class PollError(Exception):
    """An error affecting one poll but not necessarily the whole session."""

    def __init__(self, message: str, rate_limit_header: str | None = None) -> None:
        super().__init__(message)
        self.rate_limit_header = rate_limit_header


class TokenManager:
    """Obtain and proactively renew an OpenSky access token."""

    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token: str | None = None
        self.expires_at_monotonic = 0.0

    def get_access_token(self) -> str:
        """Return a valid token, refreshing it shortly before expiry."""
        if (
            self.access_token is None
            or time.monotonic() >= self.expires_at_monotonic - TOKEN_REFRESH_BUFFER_SECONDS
        ):
            self._request_new_token()
        return self.access_token

    def _request_new_token(self) -> None:
        """Exchange the API client credentials for a fresh OAuth2 token."""
        try:
            response = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
            token_data = response.json()
        except requests.RequestException as error:
            raise PollError(f"token request failed: {error}") from error
        except ValueError as error:
            raise PollError("token request returned invalid JSON") from error

        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in")
        if not access_token:
            raise PollError("token request succeeded but did not return access_token")
        try:
            expires_in_seconds = float(expires_in)
        except (TypeError, ValueError) as error:
            raise PollError("token request returned an invalid expires_in value") from error

        self.access_token = access_token
        self.expires_at_monotonic = time.monotonic() + expires_in_seconds


def load_credentials() -> tuple[str, str]:
    """Load this account's OpenSky API credentials from the project-root .env file."""
    load_dotenv(PROJECT_ROOT / ".env")
    client_id = os.environ.get(CLIENT_ID_VARIABLE, "").strip()
    client_secret = os.environ.get(CLIENT_SECRET_VARIABLE, "").strip()
    if not client_id or not client_secret:
        print(
            f"Error: Missing {CLIENT_ID_VARIABLE} or {CLIENT_SECRET_VARIABLE} in the "
            "project-root .env file.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return client_id, client_secret


def parse_rate_limit(value: str | None) -> int | None:
    """Return the numeric remaining-credit value when the header is present."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def fetch_snapshot(token_manager: TokenManager) -> tuple[pd.DataFrame, str | None]:
    """Fetch one snapshot and return it for session aggregation."""
    access_token = token_manager.get_access_token()
    try:
        response = requests.get(
            STATES_URL,
            params=MUMBAI_FIR_BOUNDS,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except requests.RequestException as error:
        raise PollError(f"states request failed: {error}") from error

    rate_limit_header = response.headers.get("X-Rate-Limit-Remaining")
    if response.status_code != 200:
        raise PollError(
            f"states request returned HTTP {response.status_code}: {response.text[:300]}",
            rate_limit_header,
        )

    try:
        response_data = response.json()
    except ValueError as error:
        raise PollError("states request returned invalid JSON", rate_limit_header) from error

    if not isinstance(response_data, dict) or "states" not in response_data:
        raise PollError("states response did not contain a states field", rate_limit_header)
    states = response_data["states"]
    if states is None:
        states = []
    if not isinstance(states, list):
        raise PollError("states response contained a non-list states field", rate_limit_header)

    # Convert OpenSky's positional state arrays into named DataFrame columns.
    try:
        dataframe = pd.DataFrame(states, columns=STATE_COLUMNS)
    except ValueError as error:
        raise PollError(
            f"states response had an unexpected state-vector shape: {error}", rate_limit_header
        ) from error
    dataframe["callsign"] = dataframe["callsign"].map(
        lambda value: value.strip() if isinstance(value, str) else value
    )
    fetch_timestamp = datetime.now(timezone.utc)
    dataframe["fetch_timestamp_utc"] = fetch_timestamp

    return dataframe, rate_limit_header


def _write_parquet_atomic(dataframe: pd.DataFrame, path: Path) -> None:
    """Write via a temporary file, then replace, so a reader never sees a half-written file."""
    temporary_path = path.with_suffix(".tmp")
    dataframe.to_parquet(temporary_path, engine="pyarrow", index=False)
    os.replace(temporary_path, path)


def partial_session_path(session_started: datetime) -> Path:
    """Location of the in-progress snapshot written while the session is still running."""
    return RAW_DATA_DIR / (
        f"session_{ACCOUNT_LABEL}_{session_started.strftime('%Y%m%d_%H%M%S')}"
        "_partial.parquet"
    )


def save_checkpoint(dataframes: list[pd.DataFrame], session_started: datetime) -> None:
    """Persist progress mid-session; a hard kill bypasses the finally block entirely."""
    if not dataframes:
        return
    try:
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _write_parquet_atomic(
            pd.concat(dataframes, ignore_index=True), partial_session_path(session_started)
        )
    except Exception as error:
        print(f"Warning: could not write checkpoint: {error}", file=sys.stderr)


def save_combined_session(dataframes: list[pd.DataFrame], session_started: datetime) -> Path | None:
    """Write all successful poll data to one Parquet file, including an empty session."""
    combined_columns = [*STATE_COLUMNS, "fetch_timestamp_utc"]
    combined_dataframe = (
        pd.concat(dataframes, ignore_index=True)
        if dataframes
        else pd.DataFrame(columns=combined_columns)
    )
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    # The account label keeps sessions from the three accounts distinguishable.
    output_path = RAW_DATA_DIR / (
        f"session_{ACCOUNT_LABEL}_{session_started.strftime('%Y%m%d_%H%M%S')}"
        "_combined.parquet"
    )
    try:
        combined_dataframe.to_parquet(output_path, engine="pyarrow", index=False)
    except Exception as error:
        print(f"Error: Could not save combined session file: {error}", file=sys.stderr)
        return None
    # The finished file supersedes the in-progress snapshot.
    partial_path = partial_session_path(session_started)
    if partial_path.exists():
        try:
            partial_path.unlink()
        except OSError as error:
            print(f"Warning: could not remove checkpoint file: {error}", file=sys.stderr)
    return output_path


def main() -> None:
    """Run polls at a fixed interval until duration, Ctrl+C, or credit threshold stops it."""
    client_id, client_secret = load_credentials()
    token_manager = TokenManager(client_id, client_secret)
    session_started = datetime.now(timezone.utc)
    session_end_monotonic = time.monotonic() + SESSION_DURATION_MINUTES * 60
    next_poll_monotonic = time.monotonic()
    collected_dataframes: list[pd.DataFrame] = []
    polls_attempted = 0
    polls_successful = 0
    stop_reason = "session duration elapsed"

    print(
        f"Starting {SESSION_DURATION_MINUTES}-minute session on account "
        f"{ACCOUNT_LABEL.upper()}; polling every {POLL_INTERVAL_SECONDS} seconds. "
        "Press Ctrl+C to stop and save collected data."
    )

    # Keep polling until the configured deadline, an interrupt, or low credits stop the session.
    try:
        while time.monotonic() < session_end_monotonic:
            sleep_seconds = next_poll_monotonic - time.monotonic()
            if sleep_seconds > 0:
                time.sleep(min(sleep_seconds, max(0, session_end_monotonic - time.monotonic())))
            if time.monotonic() >= session_end_monotonic:
                break

            polls_attempted += 1
            poll_timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
            try:
                dataframe, rate_limit_header = fetch_snapshot(token_manager)
            except PollError as error:
                print(f"{poll_timestamp} | poll failed: {error}", file=sys.stderr)
                credits_remaining = parse_rate_limit(error.rate_limit_header)
                if (
                    credits_remaining is not None
                    and credits_remaining < CREDIT_SAFETY_THRESHOLD
                ):
                    stop_reason = (
                        f"credit safety threshold reached ({credits_remaining} remaining; "
                        f"threshold is {CREDIT_SAFETY_THRESHOLD})"
                    )
                    print(f"Warning: Stopping session early because {stop_reason}.")
                    break
            else:
                collected_dataframes.append(dataframe)
                polls_successful += 1
                displayed_rate_limit = rate_limit_header or "not provided"
                print(
                    f"{poll_timestamp} | aircraft={len(dataframe)} | "
                    f"X-Rate-Limit-Remaining={displayed_rate_limit}"
                )

                if polls_successful % CHECKPOINT_EVERY_POLLS == 0:
                    save_checkpoint(collected_dataframes, session_started)

                # Stop early while enough API credits remain for a safe next run.
                credits_remaining = parse_rate_limit(rate_limit_header)
                if (
                    credits_remaining is not None
                    and credits_remaining < CREDIT_SAFETY_THRESHOLD
                ):
                    stop_reason = (
                        f"credit safety threshold reached ({credits_remaining} remaining; "
                        f"threshold is {CREDIT_SAFETY_THRESHOLD})"
                    )
                    print(f"Warning: Stopping session early because {stop_reason}.")
                    break

            # Advance the schedule from the original target time to avoid drift after quick polls.
            next_poll_monotonic += POLL_INTERVAL_SECONDS
            while next_poll_monotonic <= time.monotonic():
                next_poll_monotonic += POLL_INTERVAL_SECONDS
    except KeyboardInterrupt:
        stop_reason = "stopped manually with Ctrl+C"
        print("\nKeyboardInterrupt received; saving collected session data.")
    finally:
        # Always retain successful polls in one combined session file before exiting.
        combined_path = save_combined_session(collected_dataframes, session_started)
        total_rows = sum(len(dataframe) for dataframe in collected_dataframes)
        print("Session summary")
        print(f"Account: {ACCOUNT_LABEL.upper()}")
        print(f"Stop reason: {stop_reason}")
        print(f"Polls attempted: {polls_attempted}")
        print(f"Polls successful: {polls_successful}")
        print(f"Aircraft rows collected: {total_rows}")
        print(f"Combined Parquet file: {combined_path or 'not saved'}")


if __name__ == "__main__":
    main()
