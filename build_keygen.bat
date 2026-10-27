@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath dist_keygen --workpath build_keygen keygen.spec
if errorlevel 1 (echo Build failed. & pause & exit /b 1)
echo.
echo Keygen ready: %~dp0dist_keygen\VisionProKeygen.exe  (copy it anywhere; keep it private)
pause
