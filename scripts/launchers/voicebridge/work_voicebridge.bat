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
echo   NL CODING AGENT - PREPARA UN TASK VOICEBRIDGE
echo ============================================================
echo.
set /p "GOAL=Descrivi l'obiettivo: "
if "%GOAL%"=="" (
  echo Obiettivo vuoto. Annullato.
  pause
  exit /b 1
)

"%~dp0python\python.exe" "%~dp0nl_agent.py" work --goal "%GOAL%"
echo.
pause
