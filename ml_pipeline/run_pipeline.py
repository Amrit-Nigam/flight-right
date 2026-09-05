"""Run the whole training pipeline with one command and write a report at the end.

    python ml_pipeline/run_pipeline.py                # everything, in order
    python ml_pipeline/run_pipeline.py --from train_lstm    # resume from a step
    python ml_pipeline/run_pipeline.py --only xgboost       # one step
    python ml_pipeline/run_pipeline.py --skip encounters    # skip a slow step
    python ml_pipeline/run_pipeline.py --list               # show the steps

Steps, in order (each is an existing script; this file adds nothing to the science):

    check        ml_pipeline/check_environment.py
    preprocess   ml_pipeline/training/trajectory/preprocess_sequences.py
    train_lstm   ml_pipeline/training/trajectory/train_trajectory.py
    benchmark    ml_pipeline/training/trajectory/reference_benchmark.py
    multipath    ml_pipeline/training/trajectory/multipath.py
    encounters   ml_pipeline/training/conflict_classifier/generate_synthetic_scenarios.py
    xgboost      ml_pipeline/training/conflict_classifier/train_xgboost.py

Every step's full output is saved to ml_pipeline/reports/logs/<run>/<step>.log, and
ml_pipeline/reports/training_report_<run>.md collects the lines that matter: the
headline number, every GATE line, the per-horizon tables, calibration before/after,
and the recall-margin what-if table. The pipeline stops at the first failing step so a
broken preprocessing run can never train a model on stale data.

Why the scripts run as subprocesses rather than being imported: each one sets its own
sys.path and reads its constants at import time, and several take minutes on the GPU.
Running them exactly as a person would from the command line means the report shows
what the person would have seen.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Reports follow the data root so a smoke test in a temp directory leaves nothing behind.
DATA_ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", PROJECT_ROOT))
REPORTS = DATA_ROOT / "ml_pipeline" / "reports"

STEPS: list[tuple[str, str, str]] = [
    ("check", "ml_pipeline/check_environment.py", "environment, GPU and data presence"),
    ("preprocess", "ml_pipeline/training/trajectory/preprocess_sequences.py", "raw parquet -> chronological train/val/test windows"),
    ("train_lstm", "ml_pipeline/training/trajectory/train_trajectory.py", "Model 1: residual LSTM on the GPU"),
    ("benchmark", "ml_pipeline/training/trajectory/reference_benchmark.py", "the non-neural bar the LSTM must clear"),
    ("multipath", "ml_pipeline/training/trajectory/multipath.py", "Model 1b: route patterns + calibrated probabilities"),
    ("encounters", "ml_pipeline/training/conflict_classifier/generate_synthetic_scenarios.py", "paired real trajectories with real outcomes"),
    ("xgboost", "ml_pipeline/training/conflict_classifier/train_xgboost.py", "Model 2: conflict classifier + calibration + what-if"),
]

# Lines worth lifting into the summary. Anything matching lands in the report verbatim.
INTERESTING = re.compile(
    r"GATE|HEADLINE|headline|within 5 NM|Device:|XGBoost device|Calibration:|temperature|"
    r"Expected calibration error|Brier|Saved|Output:|Samples:|Built \d+|Scenarios:|real conflicts|"
    r"PASS|FAIL|Leakage|reproduces the label|Best checkpoint|<- current, saved|^\s+0\.0[0-2]0 "
    r"|Model card|Wrote |Rows:|Anchors|Route patterns|Dense-grid|pairs whose conflict probability",
)


def run_step(name: str, script: str, log_dir: Path, env: dict[str, str]) -> tuple[bool, float, list[str]]:
    """Run one script, stream its output to the terminal and to a log, return (ok, seconds, lines)."""
    log_path = log_dir / f"{name}.log"
    started = time.monotonic()
    print("")
    print("=" * 100)
    print(f"STEP {name}: {script}")
    print("=" * 100, flush=True)
    lines: list[str] = []
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-u", str(PROJECT_ROOT / script)],
            cwd=str(PROJECT_ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
            lines.append(line.rstrip("\n"))
        code = process.wait()
    elapsed = time.monotonic() - started
    status = "OK" if code == 0 else f"FAILED (exit {code})"
    print(f"--- {name}: {status} in {elapsed / 60:.1f} min; log {log_path}", flush=True)
    return code == 0, elapsed, lines


def extract_tables(lines: list[str]) -> list[str]:
    """Keep the blocks that are tables: runs of 3+ consecutive lines with 4+ columns of numbers."""
    out: list[str] = []
    block: list[str] = []
    for line in lines + [""]:
        numeric_columns = len(re.findall(r"-?\d+(?:\.\d+)?%?", line))
        if numeric_columns >= 4 and line.strip():
            block.append(line)
        else:
            if len(block) >= 3:
                out.extend(block + [""])
            block = []
    return out


def write_report(run_id: str, results: list[dict], started: dt.datetime) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"training_report_{run_id}.md"
    total_min = sum(r["seconds"] for r in results) / 60
    with path.open("w", encoding="utf-8") as handle:
        handle.write(f"# Flight Right training run {run_id}\n\n")
        handle.write(f"Started {started:%Y-%m-%d %H:%M} local on {platform.node()} "
                     f"({platform.system()}), Python {platform.python_version()}. "
                     f"Total {total_min:.1f} min.\n\n")
        handle.write("Read CLAUDE.md Section 1a Part 1 before quoting any number from this file: the\n"
                     "headline metric is the share of real conflicts caught with at least three minutes\n"
                     "of warning, and it lives in the `xgboost` step below.\n\n")
        handle.write("## Steps\n\n| step | status | minutes | log |\n|---|---|---|---|\n")
        for r in results:
            handle.write(f"| {r['name']} | {'OK' if r['ok'] else 'FAILED'} | {r['seconds'] / 60:.1f} | `{r['log']}` |\n")
        handle.write("\n## Gates\n\n")
        for r in results:
            for line in r["lines"]:
                if "GATE" in line:
                    handle.write(f"- **{r['name']}**: {line.strip()}\n")
        handle.write("\n## Key lines per step\n\n")
        for r in results:
            handle.write(f"### {r['name']}\n\n```\n")
            for line in r["lines"]:
                if INTERESTING.search(line):
                    handle.write(line.rstrip() + "\n")
            handle.write("```\n\n")
            tables = extract_tables(r["lines"])
            if tables:
                handle.write("<details><summary>tables</summary>\n\n```\n")
                handle.write("\n".join(tables))
                handle.write("\n```\n</details>\n\n")
        handle.write("## Artifacts\n\n")
        models = DATA_ROOT / "server" / "app" / "ml" / "saved_models"
        for artifact in sorted(models.glob("*")):
            if artifact.name != ".gitkeep":
                handle.write(f"- `{artifact.relative_to(DATA_ROOT)}` {artifact.stat().st_size / 1e6:.1f} MB\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="STEP", help="run only these steps")
    parser.add_argument("--skip", nargs="+", metavar="STEP", default=[], help="skip these steps")
    parser.add_argument("--from", dest="start_from", metavar="STEP", help="start from this step")
    parser.add_argument("--list", action="store_true", help="list steps and exit")
    parser.add_argument("--keep-going", action="store_true", help="do not stop at the first failure")
    args = parser.parse_args()

    names = [name for name, _, _ in STEPS]
    if args.list:
        for name, script, description in STEPS:
            print(f"  {name:<12} {description:<60} {script}")
        return 0
    for given in (args.only or []) + args.skip + ([args.start_from] if args.start_from else []):
        if given not in names:
            parser.error(f"unknown step {given!r}; choose from {names}")

    selected = list(STEPS)
    if args.start_from:
        selected = selected[names.index(args.start_from):]
    if args.only:
        selected = [step for step in selected if step[0] in args.only]
    selected = [step for step in selected if step[0] not in args.skip]

    started = dt.datetime.now()
    run_id = started.strftime("%Y%m%d_%H%M%S")
    log_dir = REPORTS / "logs" / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")

    print(f"Flight Right pipeline run {run_id}: {', '.join(step[0] for step in selected)}")
    results: list[dict] = []
    all_ok = True
    for name, script, _ in selected:
        ok, seconds, lines = run_step(name, script, log_dir, env)
        results.append({"name": name, "ok": ok, "seconds": seconds, "lines": lines,
                        "log": (log_dir / f"{name}.log").relative_to(DATA_ROOT)})
        if not ok:
            all_ok = False
            if not args.keep_going:
                print(f"\nStopping: step {name} failed. Fix it and re-run with --from {name}.")
                break

    report = write_report(run_id, results, started)
    print("")
    print(f"Report: {report}")
    print("Overall:", "OK" if all_ok else "FAILED -- see the report and the step log")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
