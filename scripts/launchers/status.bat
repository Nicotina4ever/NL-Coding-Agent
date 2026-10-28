@echo off
REM NL Coding Agent - persisted state summary launcher.
REM Source lives in scripts\launchers\; the portable payload stages this same file
REM at the payload root as status.bat. Root resolution below supports both layouts.
setlocal
set "ROOT=%~dp0"
if exist "%ROOT%python\python.exe" goto :root_found
set "ROOT=%~dp0..\..\"
if exist "%ROOT%python\python.exe" goto :root_found
goto :missing_runtime
:root_found
cd /d "%ROOT%"
if errorlevel 1 goto :bad_root
set "ROOT=%CD%"
set "PYTHONPATH=%ROOT%"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
set "NO_COLOR=1"
"%ROOT%\python\python.exe" "%ROOT%\nl_agent.py" status %*
set "EXITCODE=%ERRORLEVEL%"
pause
exit /b %EXITCODE%
:missing_runtime
echo ERROR: embedded Python runtime not found (expected python\python.exe under the repository or payload root).
pause
exit /b 2
:bad_root
echo ERROR: cannot enter the repository root.
pause
exit /b 2
