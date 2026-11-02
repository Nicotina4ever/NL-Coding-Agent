@echo off
REM NL Code - local launcher. Resolves everything relative to this file:
REM no absolute development path is stored here.
setlocal
set "ROOT=%~dp0"
set "PAYLOAD=%ROOT%.workspace\dist\NL Code"
if exist "%LOCALAPPDATA%\Programs\NL Code\NL Code.bat" set "PAYLOAD=%LOCALAPPDATA%\Programs\NL Code"
if not exist "%PAYLOAD%\NL Code.bat" (
    echo NL Code payload not found.
    echo Expected "%ROOT%.workspace\dist\NL Code" or an installed copy under %%LOCALAPPDATA%%\Programs\NL Code.
    pause
    exit /b 2
)
call "%PAYLOAD%\NL Code.bat" %*
exit /b %ERRORLEVEL%
