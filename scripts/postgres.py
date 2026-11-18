"""Manage the project's own PostgreSQL server.

    python scripts/postgres.py install    # download the binaries (once, ~300 MB)
    python scripts/postgres.py init       # create the cluster, roles and schema
    python scripts/postgres.py start|stop|status
    python scripts/postgres.py psql       # an interactive shell on the database

WHY A LOCAL SERVER RATHER THAN A HOSTED ONE. Postgres is a native server, so it cannot
be pip-installed into a virtual environment - a venv holds Python packages, and only the
driver (psycopg) belongs there. What it can be is *self-contained*: these are the
official EnterpriseDB binaries-only archive, unpacked inside the project, needing no
installer and no administrator rights. The alternative was a hosted Postgres, which
would make the demo depend on internet access. The map tiles already do; the database
should not.

WHERE IT LIVES. Not in the project folder: this repository is inside OneDrive, and a
database data directory inside a cloud-synced folder is slow and corruption-prone.
Everything goes under LOCALAPPDATA/FlightRight/postgres instead. `status` prints the
exact paths.

WHAT THE ROLES ARE FOR, WHICH IS THE POINT OF USING POSTGRES AT ALL.
CLAUDE.md Section 12 requires the audit log to be append-only. Under SQLite that was a
convention - "the module only contains INSERT and SELECT" - which the next person to
edit it can break silently. Here it is enforced by the database:

    flightright_owner  owns the schema and may change it (migrations only)
    flightright_app    the application role: INSERT and SELECT on audit_logs,
                       and no UPDATE or DELETE on it, ever

The backend connects as flightright_app. If it tried to rewrite a past audit entry the
database would refuse. `python scripts/postgres.py verify` demonstrates exactly that.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The cluster lives OUTSIDE the project directory, and that is deliberate.
#
# This repository sits inside a OneDrive folder. A PostgreSQL data directory is
# thousands of small files being written continuously, and putting one inside a
# cloud-synced folder is both very slow and a corruption risk - OneDrive will try to
# upload the database while it is being written to. Measured here: `initdb` into the
# project directory had not finished after 400 seconds; into %LOCALAPPDATA% it took 7.
#
# The binaries live here too, so 800 MB is not uploaded to anyone's cloud storage.
# Override with FLIGHT_RIGHT_PG_HOME if you want it somewhere else.
DEFAULT_PG_HOME = Path(
    os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "FlightRight" / "postgres"
PG_HOME = Path(os.environ.get("FLIGHT_RIGHT_PG_HOME", DEFAULT_PG_HOME))
PG_BIN = PG_HOME / "pgsql" / "bin"
PG_DATA = PG_HOME / "data"
PG_LOG = PG_HOME / "postgres.log"

# 5433 rather than the default 5432, so this cluster can never collide with a
# system-wide PostgreSQL somebody installs later.
PORT = int(os.environ.get("FLIGHT_RIGHT_PG_PORT", 5433))
HOST = "127.0.0.1"
DATABASE = "flightright"
OWNER_ROLE = "flightright_owner"
APP_ROLE = "flightright_app"
SUPERUSER = "postgres"

VERSION = "17.2-1"
DOWNLOAD_URL = f"https://get.enterprisedb.com/postgresql/postgresql-{VERSION}-windows-x64-binaries.zip"

SCHEMA = f"""
-- Section 6 of CLAUDE.md. Aircraft states stay in memory (they are re-derivable from
-- the feed and there are ~300,000 a day); what is persisted is the record of decisions,
-- which is the thing that has to survive a restart and be auditable afterwards.

CREATE TABLE IF NOT EXISTS audit_logs (
    id            BIGGENERATED,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT now(),
    level         TEXT        NOT NULL,
    source        TEXT        NOT NULL,
    action        TEXT        NOT NULL,
    user_id       TEXT,
    callsign      TEXT,
    conflict_id   TEXT,
    decision      TEXT,
    model_version TEXT,
    confidence    DOUBLE PRECISION,
    detail        JSONB       NOT NULL DEFAULT '{{}}'::jsonb
);
CREATE INDEX IF NOT EXISTS audit_timestamp ON audit_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS audit_conflict  ON audit_logs (conflict_id);
CREATE INDEX IF NOT EXISTS audit_detail    ON audit_logs USING GIN (detail);

CREATE TABLE IF NOT EXISTS conflicts (
    id                    TEXT PRIMARY KEY,
    aircraft_a            TEXT        NOT NULL,
    aircraft_b            TEXT        NOT NULL,
    first_seen            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen             TIMESTAMPTZ NOT NULL DEFAULT now(),
    tier                  SMALLINT    NOT NULL,
    severity              TEXT        NOT NULL,
    cpa_seconds           DOUBLE PRECISION,
    cpa_lateral_nm        DOUBLE PRECISION,
    cpa_vertical_ft       DOUBLE PRECISION,
    classifier_probability DOUBLE PRECISION,
    rule_is_conflict      BOOLEAN,
    model_versions        JSONB,
    reason                TEXT
);
CREATE INDEX IF NOT EXISTS conflicts_last_seen ON conflicts (last_seen DESC);

CREATE TABLE IF NOT EXISTS resolution_options (
    id                 BIGGENERATED,
    conflict_id        TEXT        NOT NULL REFERENCES conflicts(id) ON DELETE CASCADE,
    recorded_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    rank               SMALLINT    NOT NULL,
    manoeuvre_type     TEXT        NOT NULL,
    target_aircraft    TEXT        NOT NULL,
    magnitude          DOUBLE PRECISION,
    unit               TEXT,
    resulting_lateral_nm  DOUBLE PRECISION,
    resulting_vertical_ft DOUBLE PRECISION,
    seconds_to_establish  DOUBLE PRECISION,
    delay_seconds      DOUBLE PRECISION,
    fuel_equivalent_seconds DOUBLE PRECISION,
    confidence         DOUBLE PRECISION,
    score              DOUBLE PRECISION,
    residual_risk      DOUBLE PRECISION,
    new_conflict_risk  DOUBLE PRECISION,
    explanation        TEXT        NOT NULL
);
CREATE INDEX IF NOT EXISTS resolution_conflict ON resolution_options (conflict_id);

-- Plan Phase 7.3: the voice chain's two tables, created before the voice chain exists so
-- that adding it later is a producer writing rows, not a schema change. Both are
-- records of what was heard and understood, so both are append-only like the audit log.
-- Every row carries the model that produced it (the H2 lesson: modelVersion was null on
-- every audit row; that is not repeated here).
CREATE TABLE IF NOT EXISTS transcriptions (
    id            BIGGENERATED,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    clip_ref      TEXT        NOT NULL,
    heard_at      TIMESTAMPTZ,
    frequency_mhz DOUBLE PRECISION,
    transcript    TEXT        NOT NULL,
    model_id      TEXT        NOT NULL,
    quantisation  TEXT,
    asr_version   TEXT        NOT NULL,
    confidence    DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS transcriptions_heard ON transcriptions (heard_at DESC);

CREATE TABLE IF NOT EXISTS extracted_clearances (
    id               BIGGENERATED,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    transcription_id BIGINT REFERENCES transcriptions(id),
    source           TEXT        NOT NULL,
    matched_icao24   TEXT        NOT NULL,
    callsign_heard   TEXT,
    callsign_matched TEXT,
    action           TEXT        NOT NULL,
    value            DOUBLE PRECISION,
    fix              TEXT,
    confidence       DOUBLE PRECISION NOT NULL,
    issued_at        TIMESTAMPTZ NOT NULL,
    valid_seconds    DOUBLE PRECISION NOT NULL,
    applied          BOOLEAN     NOT NULL,
    report           JSONB       NOT NULL DEFAULT '{{}}'::jsonb
);
CREATE INDEX IF NOT EXISTS clearances_icao ON extracted_clearances (matched_icao24, issued_at DESC);
""".replace("BIGGENERATED", "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY")

GRANTS = f"""
GRANT USAGE ON SCHEMA public TO {APP_ROLE};

-- The audit log is append-only, and this is where that is enforced rather than
-- promised. No UPDATE. No DELETE. Not for the application role, not ever.
GRANT INSERT, SELECT ON audit_logs TO {APP_ROLE};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE};

-- Conflicts and their options are working state: the same pair is re-assessed every
-- ten seconds, so these are upserted rather than appended.
GRANT INSERT, SELECT, UPDATE, DELETE ON conflicts, resolution_options TO {APP_ROLE};

-- What was heard and what was understood from it are records, like the audit log.
GRANT INSERT, SELECT ON transcriptions, extracted_clearances TO {APP_ROLE};
"""


def binaries_present() -> bool:
    return (PG_BIN / "pg_ctl.exe").exists() or (PG_BIN / "pg_ctl").exists()


def exe(name: str) -> str:
    candidate = PG_BIN / (name + (".exe" if os.name == "nt" else ""))
    if not candidate.exists():
        raise SystemExit(f"{name} not found. Run: python scripts/postgres.py install")
    return str(candidate)


class Result:
    """What a Postgres tool did: exit code and combined output."""

    def __init__(self, returncode: int, output: str) -> None:
        self.returncode = returncode
        self.output = output
        self.stdout = output
        self.stderr = output


def run(args: list[str], password: str | None = None, timeout: int = 120) -> Result:
    """Run a Postgres tool, never interactively, never through a pipe.

    Two Windows traps are avoided here, and both of them cost hours to diagnose:

    1. **stdin must be closed.** Otherwise psql prompts for a password and waits
       forever behind captured output, which is indistinguishable from a hang.

    2. **Output goes to a FILE, not to a pipe.** initdb and pg_ctl spawn child
       processes that inherit the parent's stdout and stderr handles. With
       `capture_output=True`, Python waits for those handles to reach end-of-file -
       and a lingering `postgres.exe` grandchild holds them open indefinitely, so the
       call blocks even after the tool itself has exited. Six orphaned postgres
       processes were found doing exactly this. A file handle has no such problem.

    Every call also carries a timeout, so a failure surfaces as an error rather than
    as the whole script sitting there.
    """
    env = {**os.environ, "PGPORT": str(PORT), "PGHOST": HOST}
    if password is not None:
        env["PGPASSWORD"] = password

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as sink:
        try:
            completed = subprocess.run(args, env=env, stdin=subprocess.DEVNULL,
                                       stdout=sink, stderr=subprocess.STDOUT,
                                       timeout=timeout)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            sink.seek(0)
            return Result(1, sink.read() + f" [timed out after {timeout}s]")
        sink.seek(0)
        return Result(code, sink.read())


def install() -> None:
    if binaries_present():
        print(f"PostgreSQL binaries already present in {PG_BIN}")
        return
    PG_HOME.mkdir(parents=True, exist_ok=True)
    archive = PG_HOME / "pg.zip"
    print(f"Downloading PostgreSQL {VERSION} (~300 MB)...")
    urllib.request.urlretrieve(DOWNLOAD_URL, archive)
    print("Extracting...")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(PG_HOME)
    archive.unlink()
    print(f"Installed to {PG_HOME / 'pgsql'}")


def running() -> bool:
    if not PG_DATA.exists():
        return False
    return run([exe("pg_ctl"), "-D", str(PG_DATA), "status"]).returncode == 0


def start() -> None:
    if running():
        print(f"Already running on {HOST}:{PORT}")
        return
    result = run([exe("pg_ctl"), "-D", str(PG_DATA), "-l", str(PG_LOG),
                  "-o", f"-p {PORT} -h {HOST}", "-w", "start"])
    if result.returncode != 0:
        print(result.output)
        raise SystemExit("Failed to start PostgreSQL. See " + str(PG_LOG))
    print(f"PostgreSQL running on {HOST}:{PORT}")


def stop() -> None:
    if not running():
        print("Not running")
        return
    run([exe("pg_ctl"), "-D", str(PG_DATA), "-m", "fast", "-w", "stop"])
    print("Stopped")


def psql(database: str, sql: str, user: str = SUPERUSER,
         password: str | None = None) -> subprocess.CompletedProcess:
    # -w means "never prompt for a password": fail with an error instead of hanging.
    return run([exe("psql"), "-w", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", database,
                "-p", str(PORT), "-h", HOST, "-c", sql], password=password)


def write_env(url: str) -> None:
    """Record the connection string in the project-root .env, without disturbing it."""
    env_path = PROJECT_ROOT / ".env"
    existing = env_path.read_text() if env_path.exists() else ""
    if "DATABASE_URL" in existing:
        lines = [line for line in existing.splitlines()
                 if not line.strip().startswith("DATABASE_URL")]
        existing = "\n".join(lines)
    env_path.write_text(existing.rstrip() + f"\n\n# Local PostgreSQL (scripts/postgres.py)\nDATABASE_URL={url}\n")
    print(f"DATABASE_URL written to {env_path}")


def init() -> None:
    if PG_DATA.exists():
        print(f"Cluster already initialised at {PG_DATA}. Delete it to start over.")
        start()
        return

    password_file = PG_HOME / "superuser.pwd"
    superuser_password = secrets.token_urlsafe(24)
    app_password = secrets.token_urlsafe(24)
    password_file.write_text(superuser_password)

    print("Creating the database cluster...")
    result = run([exe("initdb"), "-D", str(PG_DATA), "-U", SUPERUSER,
                  "--auth-host=scram-sha-256", "--auth-local=scram-sha-256",
                  f"--pwfile={password_file}", "-E", "UTF8"], timeout=300)
    if result.returncode != 0:
        print(result.output)
        raise SystemExit("initdb failed")
    password_file.unlink()

    # Bind to loopback only. This cluster is for one machine and must not be reachable
    # from the network.
    with (PG_DATA / "postgresql.conf").open("a") as conf:
        conf.write(f"\n# Flight Right\nport = {PORT}\nlisten_addresses = '{HOST}'\n")

    start()

    print("Creating roles and database...")
    for statement in (
        f"CREATE ROLE {OWNER_ROLE} LOGIN PASSWORD '{app_password}'",
        f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{app_password}'",
        f"CREATE DATABASE {DATABASE} OWNER {OWNER_ROLE}",
    ):
        result = psql("postgres", statement, password=superuser_password)
        if result.returncode != 0 and "already exists" not in result.output:
            print(result.output)
            raise SystemExit("role/database creation failed")

    print("Applying the schema...")
    result = psql(DATABASE, SCHEMA, user=OWNER_ROLE, password=app_password)
    if result.returncode != 0:
        print(result.output)
        raise SystemExit("schema creation failed")

    print("Granting the application role insert-only access to the audit log...")
    result = psql(DATABASE, GRANTS, user=OWNER_ROLE, password=app_password)
    if result.returncode != 0:
        print(result.output)
        raise SystemExit("grants failed")

    url = f"postgresql://{APP_ROLE}:{app_password}@{HOST}:{PORT}/{DATABASE}"
    write_env(url)
    print("\nReady. The backend will use PostgreSQL on its next start.")


def migrate() -> None:
    """Apply the schema and grants to an EXISTING cluster. Idempotent.

    init() applies them only when the cluster is first created. Every statement here is
    CREATE ... IF NOT EXISTS or GRANT, so re-running changes nothing that already exists
    and adds only what is new (24 Sep 2026: the voice chain's two tables). Connects as
    the owner role, which shares the application role's generated password.
    """
    from urllib.parse import urlparse
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set. Run: python scripts/postgres.py init")
    password = urlparse(url).password
    if not running():
        start()
    for label, sql in (("schema", SCHEMA), ("grants", GRANTS)):
        result = psql(DATABASE, sql, user=OWNER_ROLE, password=password)
        if result.returncode != 0:
            print(result.output)
            raise SystemExit(f"{label} failed")
        print(f"applied {label}")


def verify() -> None:
    """Prove the append-only guarantee rather than asserting it."""
    import psycopg

    url = os.environ.get("DATABASE_URL")
    if not url:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
        url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set. Run: python scripts/postgres.py init")

    checks: list[tuple[str, bool, str]] = []
    with psycopg.connect(url, autocommit=True) as conn:
        version = conn.execute("SELECT version()").fetchone()[0].split(",")[0]
        checks.append(("connects to PostgreSQL", True, version))

        role = conn.execute("SELECT current_user").fetchone()[0]
        checks.append(("connects as the application role, not a superuser",
                       role == APP_ROLE, f"current_user = {role}"))

        conn.execute("INSERT INTO audit_logs (level, source, action) "
                     "VALUES ('system', 'verify', 'append-only check')")
        checks.append(("can INSERT into audit_logs", True, ""))

        for operation, sql in (("UPDATE", "UPDATE audit_logs SET action = 'tampered'"),
                               ("DELETE", "DELETE FROM audit_logs")):
            try:
                conn.execute(sql)
                checks.append((f"{operation} on audit_logs is refused", False,
                               "IT SUCCEEDED - the audit log is NOT append-only"))
            except psycopg.errors.InsufficientPrivilege as denied:
                checks.append((f"{operation} on audit_logs is refused", True,
                               str(denied).splitlines()[0]))

        for table in ("audit_logs", "conflicts", "resolution_options",
                      "transcriptions", "extracted_clearances"):
            exists = conn.execute(
                "SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",)).fetchone()[0]
            checks.append((f"table {table} exists", bool(exists), ""))

        # The voice chain's records are append-only too (plan Phase 7.3).
        for table in ("transcriptions", "extracted_clearances"):
            try:
                conn.execute(f"UPDATE {table} SET confidence = confidence")
                checks.append((f"UPDATE on {table} is refused", False, "IT SUCCEEDED"))
            except psycopg.errors.InsufficientPrivilege as denied:
                checks.append((f"UPDATE on {table} is refused", True, str(denied).splitlines()[0]))
            except psycopg.errors.UndefinedTable:
                checks.append((f"UPDATE on {table} is refused", False, "table missing - run migrate"))

    print()
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  --  {detail}" if detail else ""))
    failed = [n for n, ok, _ in checks if not ok]
    print(f"\n  {len(checks) - len(failed)} of {len(checks)} checks passed.")
    if failed:
        raise SystemExit(1)


def shell() -> None:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    url = os.environ.get("DATABASE_URL", "")
    password = url.split(":")[2].split("@")[0] if "@" in url else ""
    env = {**os.environ, "PGPASSWORD": password}
    subprocess.run([exe("psql"), "-U", APP_ROLE, "-d", DATABASE, "-p", str(PORT), "-h", HOST],
                   env=env)


def status() -> None:
    print(f"binaries : {'present' if binaries_present() else 'MISSING'}  ({PG_BIN})")
    print(f"cluster  : {'initialised' if PG_DATA.exists() else 'NOT initialised'}  ({PG_DATA})")
    print(f"server   : {'running' if running() else 'stopped'}  on {HOST}:{PORT}")


def reset() -> None:
    """Delete the cluster entirely. The binaries stay."""
    if running():
        stop()
    if PG_DATA.exists():
        shutil.rmtree(PG_DATA)
        print(f"Removed {PG_DATA}")


COMMANDS = {"install": install, "init": init, "start": start, "stop": stop,
            "status": status, "verify": verify, "psql": shell, "reset": reset,
            "migrate": migrate}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=sorted(COMMANDS))
    COMMANDS[parser.parse_args().command]()
