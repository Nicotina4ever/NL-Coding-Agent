@echo off
REM Installs NL Coder into VS Code Insiders when available, otherwise opens the VSIX.
setlocal
set "ROOT=%~dp0"
set "VSIX=%ROOT%.workspace\releases\extension\NL-Coder.vsix"
if not exist "%VSIX%" set "VSIX=%ROOT%.workspace\dist\NL-Coding-Agent-0.7.2.vsix"
if not exist "%VSIX%" (
    echo NL Coder VSIX not found. Run scripts\nlcode\build_release.ps1 first.
    pause
    exit /b 2
)
where code-insiders.cmd >nul 2>nul
if %ERRORLEVEL%==0 (
    call code-insiders.cmd --install-extension "%VSIX%" --force
    if %ERRORLEVEL%==0 (
        echo NL Coder installed in VS Code Insiders.
        pause
        exit /b 0
    )
)
start "" "%VSIX%"
exit /b 0
