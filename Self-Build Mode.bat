@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
set "NO_COLOR=1"
if not defined NL_SELFBUILD_REVIEWER_MODEL set "NL_SELFBUILD_REVIEWER_MODEL=ollama/qwen3.5:9b"
python\python.exe "%~dp0nl_agent.py" selfbuild --autonomous --project "%~dp0." --max-missions 1 --reviewer-model "%NL_SELFBUILD_REVIEWER_MODEL%"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" echo Self-Build Mode stopped with exit code %EXITCODE%.
echo State, missions, diffs, and verification runs are persisted in data\nl_coding_agent.sqlite3.
echo Resume with: python\python.exe nl_agent.py selfbuild --autonomous --project "%~dp0."
pause
exit /b %EXITCODE%
