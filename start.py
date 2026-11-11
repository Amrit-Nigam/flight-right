"""Install missing demo dependencies, verify pretrained assets, and run both servers.

No training, GitHub Release, API-key sharing or PostgreSQL installation is required.
Python 3.13 and Node.js are prerequisites. Ctrl+C stops both child servers.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT, **kwargs)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def asset_path(name):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT) or Path(name).is_absolute():
        raise ValueError("Unsafe path in demo manifest")
    return path


def verify_assets(manifest, download=True):
    pointers = []
    for entry in manifest["files"]:
        path = asset_path(entry["path"])
        if path.is_file():
            with path.open("rb") as stream:
                is_pointer = stream.read(80).startswith(b"version https://git-lfs.github.com/spec/v1")
            if is_pointer:
                pointers.append(entry["path"])
    if pointers and download:
        result = subprocess.run(["git", "lfs", "version"], cwd=ROOT, capture_output=True)
        if result.returncode:
            raise RuntimeError("Install Git LFS (https://git-lfs.com), run git lfs install, then rerun this file.")
        print("Downloading pretrained model files using Git LFS...", flush=True)
        run(["git", "lfs", "pull", "--include=" + ",".join(pointers)])
    errors = []
    for entry in manifest["files"]:
        path = asset_path(entry["path"])
        if not path.is_file() or path.stat().st_size != entry["bytes"] or digest(path) != entry["sha256"]:
            errors.append(entry["path"])
    if errors:
        raise RuntimeError("Missing/changed demo assets; run git lfs pull and restore the listed files:\n" + "\n".join(errors))


def requirements_satisfied(python):
    # Probe the chosen environment, not the Python interpreter running the launcher.
    code = '''import importlib.metadata as m,json,sys
from pathlib import Path
missing=[]
for line in Path(sys.argv[1]).read_text().splitlines():
 line=line.strip()
 if not line or line.startswith('#'):continue
 name,_,wanted=line.partition('==');name=name.split('[')[0]
 try:
  got=m.version(name)
  if wanted and got.split('+')[0]!=wanted:missing.append(name)
 except m.PackageNotFoundError:missing.append(name)
print(json.dumps(missing))
'''
    result = subprocess.run([str(python), "-c", code, str(ROOT / "server/requirements-demo.txt")],
                            capture_output=True, text=True)
    return result.returncode == 0 and json.loads(result.stdout) == []


def prepare_python(current=False, install=True):
    if sys.version_info[:2] != (3, 13):
        raise RuntimeError("Use Python 3.13: py -3.13 start.py (Windows) or python3.13 start.py")
    folder = ROOT / ".venv-demo"
    python = Path(sys.executable) if current else folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        if not install:
            raise RuntimeError("Demo environment is missing. Run again without --no-install.")
        print("Creating a separate demo Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(folder)
    if not requirements_satisfied(python):
        if not install:
            raise RuntimeError("Python runtime dependencies do not match server/requirements-demo.txt")
        print("Installing missing/pinned runtime dependencies (no training)...", flush=True)
        run([python, "-m", "pip", "install", "--upgrade", "pip"])
        # A CPU wheel avoids a CUDA toolkit requirement on a teammate's laptop.
        run([python, "-m", "pip", "install", "torch==2.13.0", "--index-url", "https://download.pytorch.org/whl/cpu"])
        run([python, "-m", "pip", "install", "-r", ROOT / "server/requirements-demo.txt"])
    run([python, "-m", "pip", "check"])
    return python


def prepare_frontend(install=True):
    node, npm = shutil.which("node"), shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        raise RuntimeError("Install Node.js 22 LTS or newer (https://nodejs.org), reopen the terminal, and rerun.")
    version = subprocess.check_output([node, "--version"], text=True).strip().lstrip("v")
    major, minor = map(int, version.split(".")[:2])
    if not (major >= 24 or (major == 22 and minor >= 12) or (major == 20 and minor >= 19)):
        raise RuntimeError("Node.js 20.19+, 22.12+ or 24+ is required by Vite.")
    lock = ROOT / "client/package-lock.json"
    stamp = ROOT / "client/node_modules/.flightright-package-lock"
    wanted = digest(lock)
    if not stamp.exists() or stamp.read_text() != wanted or not (ROOT / "client/node_modules/vite/bin/vite.js").exists():
        if not install:
            raise RuntimeError("Frontend dependencies need npm ci. Run again without --no-install.")
        subprocess.run([npm, "ci"], check=True, cwd=ROOT / "client")
        stamp.write_text(wanted)
    return node


def environment(mode, manifest):
    env = os.environ.copy()
    runtime = ROOT / "demo/.runtime"
    runtime.mkdir(exist_ok=True)
    env.update(FLIGHT_RIGHT_DATA_MODE=mode, FLIGHT_RIGHT_REPLAY_DIR=str(ROOT / "demo/replay"),
               FLIGHT_RIGHT_INTENT_HISTORY=str(ROOT / "demo/context/intent.parquet"),
               FLIGHT_RIGHT_AIRCRAFT_INFO=str(ROOT / "demo/context/aircraft_info.parquet"),
               FLIGHT_RIGHT_ROUTE_CACHE=str(ROOT / "demo/context/routes.json"),
               FLIGHT_RIGHT_VOICE_CACHE=str(ROOT / "demo/voice"),
               FLIGHT_RIGHT_SPEECH_DEMO_DIR=str(ROOT / "demo/clips"),
               FLIGHT_RIGHT_ASR_MODEL_ID=str(asset_path(manifest["speech_runtime"])),
               FLIGHT_RIGHT_ASR_DEVICE="cpu", FLIGHT_RIGHT_ROUTE_LOOKUP="off" if mode == "replay" else "on",
               FLIGHT_RIGHT_AUDIT_DB=str(runtime / "audit.sqlite3"),
               DATABASE_URL="", HF_HUB_OFFLINE="1")
    # Own-machine .env stays private. Replay doesn't need credentials; live/auto reads
    # the local .env via the existing backend configuration, never by printing its contents.
    return env


def port_available(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
        process.wait(timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        process.kill()
        process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("replay", "live", "auto"), default="replay")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="Verify/install requirements and assets, then exit")
    parser.add_argument("--no-install", action="store_true", help="Only use already-installed requirements/assets")
    parser.add_argument("--use-current-python", action="store_true", help="Use this Python environment instead of .venv-demo")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "demo/manifest.json").read_text(encoding="utf-8"))
    verify_assets(manifest, download=not args.no_install)
    python = prepare_python(args.use_current_python, not args.no_install)
    node = prepare_frontend(not args.no_install)
    if args.check:
        print("Pretrained files and dependencies verified. No training is needed.")
        return
    for port in (8000, 5173):
        if not port_available(port):
            raise RuntimeError(f"Port {port} is in use; stop that server before starting the demo.")
    env = environment(args.mode, manifest)
    if args.mode in ("live", "auto"):
        code = "from server.app.config import OPENSKY_CLIENT_ID,OPENSKY_CLIENT_SECRET; raise SystemExit(0 if OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET else 1)"
        result = subprocess.run([str(python), "-c", code], cwd=ROOT, env=env)
        if result.returncode:
            raise RuntimeError("For live/auto, copy .env.example to .env and enter your own OpenSky client ID and secret. Replay needs no keys.")
    processes = []
    flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {}
    try:
        processes.append(subprocess.Popen([str(python), "-m", "uvicorn", "server.app.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, env=env, **flags))
        processes.append(subprocess.Popen([node, "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "5173", "--strictPort"], cwd=ROOT / "client", **flags))
        for _ in range(180):
            if any(p.poll() is not None for p in processes):
                raise RuntimeError("A server stopped during startup; inspect its message above.")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1) as response:
                    health = json.load(response)
                with urllib.request.urlopen("http://127.0.0.1:5173", timeout=1):
                    pass
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("Servers did not become ready within three minutes.")
        print(f"\nDashboard: http://127.0.0.1:5173 | mode: {args.mode} | source: {health['aircraft']['source']}", flush=True)
        print("Radio samples: /radio | API: http://127.0.0.1:8000/docs | Ctrl+C stops both servers.", flush=True)
        print("Demo audit uses local SQLite; PostgreSQL-enforced immutability is not active in this launcher.", flush=True)
        if health["aircraft"].get("error"):
            print("The aircraft feed reports an error; inspect /api/health before treating the picture as current.", flush=True)
        if not args.no_browser:
            webbrowser.open("http://127.0.0.1:5173")
        while all(p.poll() is None for p in processes):
            time.sleep(1)
    finally:
        for process in reversed(processes):
            stop_process(process)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped both demo servers.")
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"\nSetup failed: {error}", file=sys.stderr)
        raise SystemExit(1)
