@echo off
REM NL Coding Agent - read-only audit of the external NL VoiceBridge Studio project.
REM Source lives in scripts\launchers\voicebridge\; this launcher is development-only
REM and is not shipped in the portable payload.
setlocal
set "ROOT=%~dp0"
if exist "%ROOT%python\python.exe" goto :root_found
set "ROOT=%~dp0..\"
if exist "%ROOT%python\python.exe" goto :root_found
set "ROOT=%~dp0..\..\"
if exist "%ROOT%python\python.exe" goto :root_found
set "ROOT=%~dp0..\..\..\"
if exist "%ROOT%python\python.exe" goto :root_found
goto :missing_runtime
:root_found
cd /d "%ROOT%"
if errorlevel 1 goto :bad_root
set "ROOT=%CD%"
set "PYTHONNOUSERSITE=1"
set "PIP_CONFIG_FILE=nul"
set "PYTHONPATH=%ROOT%"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
set "NO_COLOR=1"

echo ============================================================
echo   NL CODING AGENT - AUDIT VOICEBRIDGE - SOLA LETTURA
echo ============================================================
echo.
"%ROOT%\python\python.exe" "%ROOT%\nl_agent.py" audit %*
set "EXITCODE=%ERRORLEVEL%"
echo.
pause
exit /b %EXITCODE%
:missing_runtime
echo ERROR: embedded Python runtime not found (expected python\python.exe under the repository root).
pause
exit /b 2
:bad_root
echo ERROR: cannot enter the repository root.
pause
exit /b 2
