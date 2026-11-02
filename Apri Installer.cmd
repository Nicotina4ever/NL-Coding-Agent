@echo off
REM Opens the local installer folder. Paths are relative to this launcher.
setlocal
set "ROOT=%~dp0"
set "FOLDER=%ROOT%.workspace\releases\windows"
if not exist "%FOLDER%" mkdir "%FOLDER%"
explorer "%FOLDER%"
exit /b 0
