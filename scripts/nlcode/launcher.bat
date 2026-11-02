@echo off
rem NL Code portable launcher.
rem The Code - OSS frontend and one embedded engine runtime live in this folder.
rem Models stay in Ollama; the shared Studio engine and its data are not modified.
setlocal
set "NLCODE_ROOT=%~dp0"
if not defined NLCODE_ENGINE_ROOT set "NLCODE_ENGINE_ROOT=%~dp0__ENGINE_ROOT__"
set "NL_ENGINE_ROOT=%NLCODE_ENGINE_ROOT%"
set "ELECTRON_RUN_AS_NODE="
if not defined NL_DATA_DIR set "NL_DATA_DIR=%NLCODE_ROOT%data\engine-data"
if not defined NL_WORKSPACE_DIR set "NL_WORKSPACE_DIR=%NLCODE_ROOT%data\workspace"
if not defined NL_MODELS_CONFIG set "NL_MODELS_CONFIG=%NLCODE_ENGINE_ROOT%\config\models.yaml"
if not exist "%NL_DATA_DIR%" mkdir "%NL_DATA_DIR%"
if not exist "%NL_WORKSPACE_DIR%" mkdir "%NL_WORKSPACE_DIR%"
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
