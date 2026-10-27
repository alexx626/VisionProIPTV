@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_visionpro.ps1"
set "BUILD_EXIT=%ERRORLEVEL%"
if not "%BUILD_EXIT%"=="0" echo Build failed. Read the error above.
pause
exit /b %BUILD_EXIT%
