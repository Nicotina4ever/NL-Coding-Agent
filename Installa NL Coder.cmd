@echo off
REM Installs NL Coder into the VS Code-family editor found on this machine.
REM Supports VS Code Insiders, VS Code stable, VSCodium and Cursor when their CLI is available.
setlocal
set "ROOT=%~dp0"
set "VSIX=%ROOT%.workspace\releases\extension\NL-Coder.vsix"
if not exist "%VSIX%" set "VSIX=%ROOT%.workspace\dist\NL-Coding-Agent-0.7.2.vsix"
if not exist "%VSIX%" (
    echo NL Coder VSIX not found. Run scripts\nlcode\build_release.ps1 first.
    pause
    exit /b 2
)
set "PS=powershell"
where pwsh.exe >nul 2>nul && set "PS=pwsh"
%PS% -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\nlcode\install_nl_coder.ps1" -Vsix "%VSIX%"
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
    echo.
    echo Automatic install did not complete. You can install manually with:
    echo   code --install-extension "%VSIX%"
    echo   code-insiders --install-extension "%VSIX%"
)
pause
exit /b %CODE%
