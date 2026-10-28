@echo off
cd /d "%~dp0"
set "PYTHONPATH=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NO_COLOR=1"
python\python.exe "%~dp0nl_agent.py" status
pause
