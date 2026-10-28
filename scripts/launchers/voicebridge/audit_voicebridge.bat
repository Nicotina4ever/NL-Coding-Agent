@echo off
setlocal
cd /d "%~dp0"

set "PYTHONNOUSERSITE=1"
set "PIP_CONFIG_FILE=nul"
set "PYTHONPATH=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NO_COLOR=1"

echo ============================================================
echo   NL CODING AGENT - AUDIT VOICEBRIDGE - SOLA LETTURA
echo ============================================================
echo.
"%~dp0python\python.exe" "%~dp0nl_agent.py" audit
echo.
pause
