"""Look at what the backend has stored in PostgreSQL, without opening a database shell.

    python scripts/db_view.py                      # every table, its row count, its columns
    python scripts/db_view.py audit_logs           # the 20 newest rows of one table
    python scripts/db_view.py audit_logs -n 50     # ... the 50 newest
    python scripts/db_view.py conflicts --csv out.csv            # export a whole table
    python scripts/db_view.py --sql "SELECT decision, count(*) FROM audit_logs GROUP BY 1"

Tables: audit_logs (every controller and system decision, append-only), conflicts (each alarm
or watch-list pair the backend raised), resolution_options (the manoeuvres Model 3 offered for
them), transcriptions and extracted_clearances (what the speech chain heard and did).

Connects with DATABASE_URL from .env, i.e. as the application role, which PostgreSQL only lets
INSERT and SELECT on the audit tables. This script is read-only on top of that: --sql refuses
anything but a SELECT / WITH query. Needs the database running (python scripts/postgres.py start).
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
TABLES = ["audit_logs", "conflicts", "resolution_options", "transcriptions", "extracted_clearances"]
ORDER = {"audit_logs": "id", "conflicts": "last_seen", "resolution_options": "id",
         "transcriptions": "id", "extracted_clearances": "id"}


def connect() -> psycopg.Connection:
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        sys.exit("DATABASE_URL is not set in .env - run: python scripts/postgres.py init")
    try:
        return psycopg.connect(url, autocommit=True)
    except psycopg.OperationalError as failure:
        sys.exit(f"Cannot reach PostgreSQL ({type(failure).__name__}). Start it: python scripts/postgres.py start")


def show(rows: list[tuple], names: list[str], width: int = 60) -> None:
    cells = [[("" if v is None else str(v)).replace("\n", " ")[:width] for v in row] for row in rows]
    widths = [max([len(n)] + [len(r[i]) for r in cells]) for i, n in enumerate(names)]
    print("  ".join(n.ljust(w) for n, w in zip(names, widths)))
    print("  ".join("-" * w for w in widths))
    for row in cells:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))


def overview(conn: psycopg.Connection) -> None:
    for table in TABLES:
        count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        columns = [r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
            (table,))]
        print(f"{table:22s} {count:7d} rows   {', '.join(columns)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table", nargs="?", choices=TABLES)
    ap.add_argument("-n", type=int, default=20, help="rows to show (newest first)")
    ap.add_argument("--csv", help="write the whole table to this CSV file")
    ap.add_argument("--sql", help="run one SELECT query and print the result")
    args = ap.parse_args()
    conn = connect()

    if args.sql:
        if not args.sql.lstrip().lower().startswith(("select", "with")):
            sys.exit("Only SELECT / WITH queries are allowed here.")
        cursor = conn.execute(args.sql)
        show(cursor.fetchall(), [d.name for d in cursor.description])
    elif args.table and args.csv:
        cursor = conn.execute(f"SELECT * FROM {args.table} ORDER BY {ORDER[args.table]}")
        with open(args.csv, "w", newline="", encoding="utf8") as handle:
            writer = csv.writer(handle)
            writer.writerow([d.name for d in cursor.description])
            writer.writerows(cursor.fetchall())
        print(f"wrote {args.csv}")
    elif args.table:
        cursor = conn.execute(f"SELECT * FROM {args.table} ORDER BY {ORDER[args.table]} DESC LIMIT %s", (args.n,))
        show(cursor.fetchall(), [d.name for d in cursor.description])
    else:
        overview(conn)


if __name__ == "__main__":
    main()
