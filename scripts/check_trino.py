"""Phase 2.1, 2.2 and 2.3 — is the OpenSky historical archive open to us, and does it
hold Indian traffic low down?

Three questions, in dependency order. 2.2 and 2.3 are queries *through* Trino, so 2.1
gates both.

  2.1  Can we authenticate, and can we execute a query?
  2.2  Is there a target-state table (selected altitude)?  If not, nothing may be built
       on selected altitude - that is a permanent scope decision, not a delay.
  2.3  Does the archive hold Mumbai traffic, and does it hold it BELOW 10,000 ft?

**Authentication vs authorisation are different failures and this script separates them.**
pyopensky authenticates Trino with `grant_type=password` against the OpenSky *website*
account - username and password - with `client_id` hardcoded to "trino-client". It does
NOT use the clientId/clientSecret pairs used for REST state-vector polling. A valid token
therefore proves the account exists and the password is right; it proves nothing about
whether the account may run a query.

**Every query must filter on the partition column** - `hour` for `state_vectors_data4`,
`day` for `flights_data4` - or the server rejects it outright. That is not an
optimisation, it is a requirement.

Run:  python scripts/check_trino.py
Writes a dated JSON beside the other reports.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "ml_pipeline" / "reports"

TOKEN_URL = ("https://auth.opensky-network.org/auth/realms/"
             "opensky-network/protocol/openid-connect/token")

# Mumbai demo box (CLAUDE.md Section 2) and the en-route floor used everywhere else.
LAT_MIN, LAT_MAX = 16.0, 23.5
LON_MIN, LON_MAX = 68.0, 77.5
VABB_LAT, VABB_LON = 19.0887, 72.8679
LOW_ALTITUDE_M = 3048.0          # 10,000 ft, the conflict-detection floor
NEAR_VABB_NM = 60.0

# The tables pyopensky's own schema declares. This mirrors the server side, so it answers
# 2.2 even when a query cannot be run.
KNOWN_TABLES = ["state_vectors_data4", "flights_data4", "flights_data5", "acas_data4",
                "allcall_replies_data4", "identification_data4", "operational_status_data4",
                "position_data4", "rollcall_replies_data4", "velocity_data4", "flarm_raw"]


def check_auth() -> dict:
    """2.1a - does the account authenticate at all?"""
    import httpx
    from pyopensky.config import trino_password, trino_username

    if not trino_username or not trino_password:
        return {"configured": False,
                "detail": "username/password empty in pyopensky settings.conf"}
    try:
        response = httpx.post(TOKEN_URL, timeout=60, data={
            "client_id": "trino-client", "grant_type": "password",
            "username": trino_username, "password": trino_password})
    except Exception as failure:                                   # noqa: BLE001
        return {"configured": True, "authenticated": False, "detail": type(failure).__name__}

    if response.status_code != 200:
        return {"configured": True, "authenticated": False,
                "http_status": response.status_code,
                "detail": response.json().get("error_description", "")[:200]
                if response.headers.get("content-type", "").startswith("application/json")
                else response.text[:200]}
    return {"configured": True, "authenticated": True,
            "expires_in": response.json().get("expires_in")}


def check_authorisation() -> dict:
    """2.1b - may the account execute a query? `SELECT 1` touches no table, so a refusal
    here is a blanket permission problem rather than a table or partition problem."""
    from pyopensky.trino import Trino
    probes = [("trivial (no table)", "SELECT 1 AS n"),
              ("metadata", "SHOW TABLES")]
    results = {}
    for label, sql in probes:
        try:
            Trino().query(sql)
            results[label] = "OK"
        except Exception as failure:                               # noqa: BLE001
            text = str(failure)
            results[label] = ("PERMISSION_DENIED" if "PERMISSION_DENIED" in text
                              else type(failure).__name__)
    return {"probes": results, "authorised": results.get("trivial (no table)") == "OK"}


def question_2_2(authorised: bool) -> dict:
    """Is there a table holding selected altitude?"""
    finding = {
        "known_tables": KNOWN_TABLES,
        "target_state_table_present": False,
        "capability_flag_only": "operational_status_data4.supportstargetstatereport",
        "conclusion": ("The archive records WHICH aircraft are capable of broadcasting a "
                       "Target State report, and does not record WHAT they broadcast. "
                       "There is no selected-altitude table."),
        "verified_directly": False,
    }
    if authorised:
        try:
            from pyopensky.trino import Trino
            tables = Trino().query("SHOW TABLES")
            names = [str(v).lower() for v in tables.iloc[:, 0]]
            finding["server_tables"] = names
            finding["target_state_table_present"] = any("target" in n for n in names)
            finding["verified_directly"] = True
        except Exception as failure:                               # noqa: BLE001
            finding["error"] = type(failure).__name__
    return finding


def sample_hours(year: int, month: int) -> list[int]:
    """Three representative hours in a month: the 15th at 00, 08 and 16 UTC.

    A whole month is NOT counted, deliberately. One hour of the Mumbai box is ~175,000
    state vectors, so a month is of order 126 million rows and the server refuses the
    query. Three spread hours answer "is the traffic there" for a thousandth of the cost,
    and every number derived from them is reported as a per-hour rate, never as a total.
    """
    base = datetime(year, month, 15, tzinfo=timezone.utc)
    return [int((base.replace(hour=h)).timestamp()) for h in (0, 8, 16)]


def question_2_3(authorised: bool, months: int = 36) -> dict:
    """Test A: is there Mumbai traffic at all? Test B: is there any BELOW 10,000 ft?

    Test B is the one that matters. Low-altitude reception needs a receiver near the
    airport, so Test A can look healthy on cruise traffic overflying the box while the
    arrival traffic we actually need is absent.

    Both tests run in ONE query per month via conditional aggregation, so the expensive
    partition scan is paid once rather than twice.
    """
    if not authorised:
        return {"ran": False, "reason": "Trino authorisation denied; see question 2.1."}

    from pyopensky.trino import Trino
    trino = Trino()
    now = datetime.now(timezone.utc)
    near_metres = NEAR_VABB_NM * 1852.0
    results = []

    for back in range(months):
        index = (now.year * 12 + now.month - 1) - back
        year, month = divmod(index, 12)
        month += 1
        hours = sample_hours(year, month)
        if hours[0] > int(now.timestamp()):
            continue
        partitions = ", ".join(str(h) for h in hours)
        distance = (f"ST_Distance(to_spherical_geography(ST_Point(lon, lat)), "
                    f"to_spherical_geography(ST_Point({VABB_LON}, {VABB_LAT})))")
        sql = f"""
            SELECT count(*) AS box_rows,
                   count(DISTINCT icao24) AS box_aircraft,
                   count(CASE WHEN baroaltitude < {LOW_ALTITUDE_M}
                               AND {distance} < {near_metres} THEN 1 END) AS low_rows,
                   count(DISTINCT CASE WHEN baroaltitude < {LOW_ALTITUDE_M}
                               AND {distance} < {near_metres} THEN icao24 END) AS low_aircraft
            FROM state_vectors_data4
            WHERE hour IN ({partitions})
              AND lat BETWEEN {LAT_MIN} AND {LAT_MAX}
              AND lon BETWEEN {LON_MIN} AND {LON_MAX}"""
        label = f"{year:04d}-{month:02d}"
        try:
            frame = trino.query(sql)
            results.append({
                "month": label, "hours_sampled": len(hours),
                "box_rows": int(frame["box_rows"][0]),
                "box_aircraft": int(frame["box_aircraft"][0]),
                "low_rows": int(frame["low_rows"][0]),
                "low_aircraft": int(frame["low_aircraft"][0]),
            })
            print(f"     {label}   box {results[-1]['box_rows']:>9,} rows "
                  f"/ {results[-1]['box_aircraft']:>4} ac    "
                  f"low+near {results[-1]['low_rows']:>8,} rows / {results[-1]['low_aircraft']:>4} ac")
        except Exception as failure:                               # noqa: BLE001
            results.append({"month": label, "error": type(failure).__name__})
            print(f"     {label}   ERROR {type(failure).__name__}")

    good = [r for r in results if "error" not in r]
    covered = [r for r in good if r["box_rows"] > 0]
    low_covered = [r for r in good if r["low_rows"] > 0]
    return {
        "ran": True,
        "sampling": "the 15th of each month at 00, 08 and 16 UTC",
        "months_queried": len(results),
        "months_with_box_data": len(covered),
        "months_with_low_data": len(low_covered),
        "earliest_month_with_low_data": min((r["month"] for r in low_covered), default=None),
        "per_month": results,
    }


def main() -> int:
    print("=" * 88)
    print("PHASE 2.1 / 2.2 / 2.3 -- OpenSky historical archive access and Indian coverage")
    print("=" * 88)

    auth = check_auth()
    print(f"\n2.1a authentication : configured={auth.get('configured')} "
          f"authenticated={auth.get('authenticated')} {auth.get('detail','')}")

    authz = {"authorised": False, "probes": {}}
    if auth.get("authenticated"):
        authz = check_authorisation()
        for label, outcome in authz["probes"].items():
            print(f"2.1b {label:20}: {outcome}")
    print(f"\n2.1  -> QUERIES ALLOWED: {authz['authorised']}")
    if auth.get("authenticated") and not authz["authorised"]:
        print("     Authentication succeeds and authorisation does not. `SELECT 1` touches no")
        print("     table, so this is not a partition filter or a table-permission problem:")
        print("     the account has no query permission on Trino at all.")

    q22 = question_2_2(authz["authorised"])
    print(f"\n2.2  target-state table present: {q22['target_state_table_present']} "
          f"(verified directly: {q22['verified_directly']})")
    print(f"     {q22['conclusion']}")

    print("\n2.3  Test A (Mumbai box) / Test B (below 10,000 ft within 60 NM of VABB)")
    print("     sampling the 15th of each month at 00, 08 and 16 UTC")
    q23 = question_2_3(authz["authorised"])
    if not q23["ran"]:
        print(f"     NOT RUN -- {q23['reason']}")
    else:
        print(f"\n     months queried {q23['months_queried']} | "
              f"with Mumbai-box data {q23['months_with_box_data']} | "
              f"with LOW data near VABB {q23['months_with_low_data']}")
        print(f"     earliest month carrying low-altitude data: {q23['earliest_month_with_low_data']}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"trino_access_{stamp}.json"
    out.write_text(json.dumps({"measured_at_utc": datetime.now(timezone.utc).isoformat(),
                               "question_2_1": {"authentication": auth, "authorisation": authz},
                               "question_2_2": q22, "question_2_3": q23}, indent=2))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
