@echo off
cd /d "%~dp0"
py -3.13 --version >nul 2>&1
if not errorlevel 1 (
  py -3.13 start.py %*
) else (
  python start.py %*
)
if errorlevel 1 pause
