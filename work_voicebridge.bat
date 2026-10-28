@echo off
setlocal
cd /d "%~dp0"

set "PYTHONNOUSERSITE=1"
set "PIP_CONFIG_FILE=nul"

echo ============================================================
echo   NL CODING AGENT - PREPARA UN TASK VOICEBRIDGE
echo ============================================================
echo.
set /p "GOAL=Descrivi l'obiettivo: "
if "%GOAL%"=="" (
  echo Obiettivo vuoto. Annullato.
  pause
  exit /b 1
)

"%~dp0python\python.exe" -m nl_coding_agent.main work --goal "%GOAL%"
echo.
pause
