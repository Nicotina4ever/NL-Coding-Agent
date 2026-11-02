# Creates Windows desktop and Start-menu shortcuts for the local NL Code checkout.
# The shortcuts point at the repository launchers, whose own targets are resolved
# relative to %~dp0; no engine/runtime copy is created.
[CmdletBinding()]
param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$icon = Join-Path $repo '.workspace\dist\NL Code\NL Code.exe'
if (-not (Test-Path $icon)) { $icon = Join-Path $repo 'assets\LogoMio.svg' }
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$programs = Join-Path ([Environment]::GetFolderPath('Programs')) 'NL Code'
$items = @(
    @{ Name = 'Avvia NL Code'; File = 'Avvia NL Code.cmd'; Description = 'Avvia NL Code standalone' },
    @{ Name = 'Apri Installer'; File = 'Apri Installer.cmd'; Description = 'Apre la cartella degli installer' },
    @{ Name = 'Installa NL Coder'; File = 'Installa NL Coder.cmd'; Description = 'Installa NL Coder in VS Code Insiders' },
    @{ Name = 'GitHub Releases'; File = 'GitHub Releases.cmd'; Description = 'Apre le release GitHub' }
)
if ($Remove) {
    foreach ($item in $items) {
        Remove-Item (Join-Path $desktop ($item.Name + '.lnk')) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $programs -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'Shortcuts removed.'
    return
}
function New-NlShortcut([string]$Path, [string]$Launcher, [string]$Description) {
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = Join-Path $env:WINDIR 'System32\cmd.exe'
    $shortcut.Arguments = '/c ""' + (Join-Path $repo $Launcher) + '""'
    $shortcut.WorkingDirectory = $repo
    $shortcut.Description = $Description
    if ($icon.EndsWith('.exe')) { $shortcut.IconLocation = $icon + ',0' }
    $shortcut.Save()
}
New-Item -ItemType Directory -Force -Path $programs | Out-Null
foreach ($item in $items) {
    New-NlShortcut (Join-Path $desktop ($item.Name + '.lnk')) $item.File $item.Description
    New-NlShortcut (Join-Path $programs ($item.Name + '.lnk')) $item.File $item.Description
}
Write-Host ('Desktop/Start shortcuts created for ' + $repo)
