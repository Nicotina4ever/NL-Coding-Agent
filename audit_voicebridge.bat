@echo off
setlocal
cd /d "%~dp0"

set "PYTHONNOUSERSITE=1"
set "PIP_CONFIG_FILE=nul"

echo ============================================================
echo   NL CODING AGENT - AUDIT VOICEBRIDGE - SOLA LETTURA
echo ============================================================
echo.
"%~dp0python\python.exe" -m nl_coding_agent.main audit
echo.
pause
