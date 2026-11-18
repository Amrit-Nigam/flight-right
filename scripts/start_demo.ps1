# Start everything for the demo, fresh:   powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
#
# 1. PostgreSQL (no-op if already running).
# 2. Stops a Flight Right backend already on port 8000 (only ours: its command line must contain
#    server.app.main) and starts a new one in REPLAY mode in its own window. A fresh start matters:
#    the replay clock runs from startup and the demo alarm arrives about 4 minutes later.
# 3. Keeps the previous model trace as model_trace_previous.log, so the new one starts empty.
# 4. Starts the dashboard (npm run dev) in its own window if it is not already running.
# 5. Opens the dashboard, and model_trace.log in VS Code if the `code` command exists.
param([string]$Mode = "replay")

$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root "venv\Scripts\python.exe"
Set-Location $root

& $python scripts\postgres.py start

$listening = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($conn in $listening) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $($conn.OwningProcess)"
    if ($proc.CommandLine -like "*server.app.main*") {
        Write-Host "Stopping the old Flight Right backend (PID $($conn.OwningProcess))"
        Stop-Process -Id $conn.OwningProcess -Force
        Start-Sleep -Seconds 2
    } else {
        Write-Host "Port 8000 is held by another program: $($proc.CommandLine)" -ForegroundColor Red
        Write-Host "Close it and run this script again." -ForegroundColor Red
        exit 1
    }
}

$logs = Join-Path $root "server\logs"
New-Item -ItemType Directory -Force $logs | Out-Null
if (Test-Path "$logs\model_trace.log") { Move-Item -Force "$logs\model_trace.log" "$logs\model_trace_previous.log" }

$backend = "Set-Location '$root'; `$env:FLIGHT_RIGHT_DATA_MODE='$Mode'; & '$python' -m uvicorn server.app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backend
Write-Host "Backend starting in $Mode mode (models take about 15 s to load)"

if (-not (Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\client'; npm run dev"
    Write-Host "Dashboard starting"
}

Start-Sleep -Seconds 20
Start-Process "http://localhost:5173"
if (Get-Command code -ErrorAction SilentlyContinue) { code "$logs\model_trace.log" }
Write-Host "Ready. The watch-list entry appears about 3.5 min after the backend started, the alarm about 4 min."
