@echo off
REM Hermes Companion - one-click installer (Windows)
REM Double-click this file. It opens PowerShell as Administrator and runs the guided setup.
setlocal
set "HERE=%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting administrator rights...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%HERE%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\bootstrap-windows.ps1"
echo.
if %errorlevel% neq 0 (
  echo Install did not finish. Read the message above, or open docs\AGENT_INSTALL_GUIDE.md.
) else (
  echo Done. Open http://127.0.0.1:8787 in your browser and sign in.
  echo For your phone, read docs\PHONE_ACCESS.md
)
pause
