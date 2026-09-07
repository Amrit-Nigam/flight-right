"""Live aircraft states from OpenSky, with the credit brake the collection scripts use.

The deleted Node provider authenticated with a username and password over HTTP Basic.
OpenSky retired that; the project's .env carries an OAuth2 client-credentials pair
instead, and the collection scripts in ml_pipeline/ingestion already speak that protocol.
This client uses the same token flow so there is one way to talk to OpenSky, not two.

Credits matter and the numbers are recorded in CLAUDE.md (30 Aug 2026): the Mumbai box
costs 2 credits per poll against a 4,000-credit rolling 24-hour cap, and the cap is a
rolling window rather than a daily reset. `X-Rate-Limit-Remaining` is returned on the
authenticated endpoint, so the brake below is real rather than advisory.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests

from ..config import (BOUNDS, OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET,
                      OPENSKY_STATES_URL, OPENSKY_TOKEN_URL)

log = logging.getLogger("flightright.opensky")

TOKEN_REFRESH_BUFFER_SECONDS = 60
# Stop using live data below this many remaining credits, leaving headroom for the
# scheduled collection runs that feed model training.
CREDIT_SAFETY_THRESHOLD = 200


class OpenSkyUnavailable(RuntimeError):
    """Raised whenever live data cannot be served, so the caller can fall back."""


@dataclass
class OpenSkyClient:
    client_id: str = OPENSKY_CLIENT_ID
    client_secret: str = OPENSKY_CLIENT_SECRET
    access_token: str | None = field(default=None, repr=False)
    expires_at: float = 0.0
    credits_remaining: int | None = None

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _token(self) -> str:
        if self.access_token and time.monotonic() < self.expires_at - TOKEN_REFRESH_BUFFER_SECONDS:
            return self.access_token
        if not self.configured:
            raise OpenSkyUnavailable(
                "OPENSKY_CLIENT_ID / OPENSKY_CLIENT_SECRET are not set in the project-root .env")
        try:
            response = requests.post(
                OPENSKY_TOKEN_URL,
                data={"grant_type": "client_credentials",
                      "client_id": self.client_id, "client_secret": self.client_secret},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise OpenSkyUnavailable(f"token request failed: {error}") from error

        token = payload.get("access_token")
        if not token:
            raise OpenSkyUnavailable("token request returned no access_token")
        self.access_token = token
        self.expires_at = time.monotonic() + float(payload.get("expires_in", 1800))
        return token

    def fetch_states(self) -> list[list]:
        """Raw OpenSky state vectors inside the Mumbai box.

        Raises OpenSkyUnavailable rather than returning empty, so the caller can tell
        "no aircraft right now" apart from "the feed is down" and fall back accordingly.
        """
        token = self._token()
        params = {"lamin": BOUNDS["lat_min"], "lamax": BOUNDS["lat_max"],
                  "lomin": BOUNDS["lon_min"], "lomax": BOUNDS["lon_max"]}
        try:
            response = requests.get(OPENSKY_STATES_URL, params=params,
                                    headers={"Authorization": f"Bearer {token}"}, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise OpenSkyUnavailable(f"states request failed: {error}") from error

        remaining = response.headers.get("X-Rate-Limit-Remaining")
        if remaining is not None:
            try:
                self.credits_remaining = int(remaining)
            except ValueError:
                pass
        if self.credits_remaining is not None and self.credits_remaining < CREDIT_SAFETY_THRESHOLD:
            raise OpenSkyUnavailable(
                f"only {self.credits_remaining} OpenSky credits left, below the "
                f"{CREDIT_SAFETY_THRESHOLD} reserve kept for scheduled collection")

        states = payload.get("states") or []
        log.info("OpenSky returned %d states, %s credits remaining",
                 len(states), self.credits_remaining if self.credits_remaining is not None else "?")
        return states
