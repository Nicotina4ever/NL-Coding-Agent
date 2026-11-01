@echo off
rem NL Code portable launcher.
rem The Code - OSS frontend is self-contained in this folder; the NL Coding
rem Engine stays in its existing installation so models, agents, permissions,
rem missions and history are the same data the Studio uses.
setlocal
set "NLCODE_ROOT=%~dp0"
if not defined NLCODE_ENGINE_ROOT set "NLCODE_ENGINE_ROOT=__ENGINE_ROOT__"
set "NL_ENGINE_ROOT=%NLCODE_ENGINE_ROOT%"
set "ELECTRON_RUN_AS_NODE="
rem Reuse the engine's existing data (settings, agents, models, permissions, history).
if not defined NL_DATA_DIR if exist "%NLCODE_ENGINE_ROOT%\data" set "NL_DATA_DIR=%NLCODE_ENGINE_ROOT%\data"
if not exist "%NLCODE_ENGINE_ROOT%\nl_agent.py" goto missing_engine
if not exist "%NLCODE_ENGINE_ROOT%\python\python.exe" goto missing_engine
if not exist "%NLCODE_ROOT%__APP_EXE__" goto missing_app
start "" "%NLCODE_ROOT%__APP_EXE__" %*
exit /b 0

:missing_engine
echo [NL Code] NL Coding Engine not found at "%NLCODE_ENGINE_ROOT%".
echo [NL Code] Set NLCODE_ENGINE_ROOT to the folder that contains nl_agent.py and python\python.exe.
pause
exit /b 2

:missing_app
echo [NL Code] "__APP_EXE__" not found next to this launcher.
pause
exit /b 3
