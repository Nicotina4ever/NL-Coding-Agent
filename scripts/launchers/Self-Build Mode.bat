@echo off
REM NL Coding Agent - guarded Self-Build Mode launcher (one bounded mission).
REM Source lives in scripts\launchers\; the portable payload stages this same file
REM at the payload root as "Self-Build Mode.bat".
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
if not defined NL_SELFBUILD_REVIEWER_MODEL set "NL_SELFBUILD_REVIEWER_MODEL=ollama/qwen3.5:9b"
"%ROOT%\python\python.exe" "%ROOT%\nl_agent.py" selfbuild --autonomous --project "%ROOT%\." --max-missions 1 --reviewer-model "%NL_SELFBUILD_REVIEWER_MODEL%" %*
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" echo Self-Build Mode stopped with exit code %EXITCODE%.
echo State, missions, diffs, and verification runs are persisted in data\nl_coding_agent.sqlite3.
echo Resume with: python\python.exe nl_agent.py selfbuild --autonomous --project "%ROOT%\."
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
