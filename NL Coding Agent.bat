@echo off
REM NL Coding Agent - single user-facing launcher kept at the repository root.
REM The portable payload stages this same file at the payload root.
REM It resolves the repository/payload root, so it works when double-clicked or
REM started from any working directory.
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
"%ROOT%\python\python.exe" "%ROOT%\nl_agent.py" gui %*
set "EXITCODE=%ERRORLEVEL%"
exit /b %EXITCODE%
:missing_runtime
echo ERROR: embedded Python runtime not found next to this launcher.
pause
exit /b 2
:bad_root
echo ERROR: cannot enter the repository root.
pause
exit /b 2
