# Installs the NL Coder VSIX into the VS Code-family CLI the user has.
# Works on Windows PowerShell 5.1+/7, macOS and Linux. The VSIX itself is portable;
# only the command used to install it differs per editor and OS.
[CmdletBinding()]
param(
    [string]$Vsix = '',
    [string]$Cli = '',
    [switch]$List
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Vsix) {
    foreach ($candidate in @(
        (Join-Path $repo '.workspace\releases\extension\NL-Coder.vsix'),
        (Join-Path $repo '.workspace\dist\NL-Coding-Agent-0.7.2.vsix')
    )) {
        if (Test-Path $candidate) { $Vsix = $candidate; break }
    }
}
if (-not $Vsix -or -not (Test-Path $Vsix)) { throw 'NL-Coder.vsix not found; run scripts/nlcode/build_release.ps1 first.' }
$Vsix = (Resolve-Path $Vsix).Path

$names = @('code-insiders', 'code', 'codium', 'cursor')
$found = New-Object System.Collections.Generic.List[object]
foreach ($name in $names) {
    $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        $found.Add([pscustomobject]@{ Name = $name; Path = $command.Source }) | Out-Null
    }
}
$common = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code Insiders\bin\code-insiders.cmd'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Microsoft VS Code\bin\code.cmd'),
    '/Applications/Visual Studio Code - Insiders.app/Contents/Resources/app/bin/code-insiders',
    '/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code',
    '/usr/bin/code',
    '/usr/local/bin/code',
    '/snap/bin/code',
    '/usr/bin/codium'
)
foreach ($path in $common) {
    if ($path -and (Test-Path $path)) {
        $entry = $found | Where-Object { $_.Path -eq $path } | Select-Object -First 1
        if (-not $entry) { $found.Add([pscustomobject]@{ Name = [System.IO.Path]::GetFileNameWithoutExtension($path); Path = $path }) | Out-Null }
    }
}
if ($List -or $found.Count -eq 0) {
    if ($found.Count -eq 0) {
        Write-Host 'No VS Code-family CLI found in PATH or common locations.'
        Write-Host 'Install the VSIX manually: <editor> --install-extension "' + $Vsix + '"'
        if ($List) { return }
        exit 2
    }
    $found | ForEach-Object { Write-Host ($_.Name + ' -> ' + $_.Path) }
    if ($List) { return }
}
$selected = $null
if ($Cli) {
    $match = $found | Where-Object { $_.Name -eq $Cli -or $_.Path -eq $Cli } | Select-Object -First 1
    if (-not $match) { $match = [pscustomobject]@{ Name = $Cli; Path = $Cli } }
    $selected = $match
} elseif ($found.Count -eq 1) {
    $selected = $found[0]
} else {
    Write-Host 'Multiple VS Code-family editors found:'
    for ($i = 0; $i -lt $found.Count; $i++) { Write-Host ('  [' + ($i + 1) + '] ' + $found[$i].Name + ' -> ' + $found[$i].Path) }
    $answer = Read-Host ('Choose 1-' + $found.Count + ' or press Enter for 1')
    if ([string]::IsNullOrWhiteSpace($answer)) { $selected = $found[0] }
    else {
        $index = 0
        if ([int]::TryParse($answer, [ref]$index) -and $index -ge 1 -and $index -le $found.Count) {
            $selected = $found[$index - 1]
        }
    }
}
if (-not $selected) { throw 'No editor selected; nothing installed.' }
Write-Host ('Installing NL Coder into ' + $selected.Name + ' (' + $selected.Path + ')')
& $selected.Path --install-extension $Vsix --force
if ($LASTEXITCODE -ne 0) {
    throw ('Extension installation failed (exit ' + $LASTEXITCODE + '). Manual command: ' + $selected.Name + ' --install-extension "' + $Vsix + '"')
}
Write-Host 'NL Coder installed. Reload the editor window to activate it.'
