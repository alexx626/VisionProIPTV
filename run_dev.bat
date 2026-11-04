@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
start "" /b venv\Scripts\python.exe main.py > logs\run_dev.log 2>&1
