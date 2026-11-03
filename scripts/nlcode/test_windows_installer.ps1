# Verifies the real Windows installer lifecycle: custom path with spaces, custom
# data root, launch, upgrade preserving path/settings, complete uninstall keeping
# personal data by default, and optional data removal.
[CmdletBinding()]
param(
    [string]$Setup = '',
    [string]$Root = ''
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Setup) { $Setup = Join-Path $repo '.workspace\releases\windows\NL-Code-Setup.exe' }
if (-not (Test-Path $Setup)) { throw "installer not found: $Setup" }
if (-not $Root) {
    $drive = if (Test-Path 'K:\') { 'K:\' } else { $env:SystemDrive + '\' }
    $Root = Join-Path $drive ('NL Code Installer Test ' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
$install = Join-Path $Root 'App Folder'
$data = Join-Path $Root 'Data Folder'
$results = New-Object System.Collections.Generic.List[object]
function Check([string]$name, [bool]$ok, [string]$detail = '') {
    $results.Add([pscustomobject]@{ name = $name; ok = $ok; detail = $detail })
    $status = if ($ok) { 'PASS' } else { 'FAIL' }
    $suffix = if ($detail) { ' — ' + $detail } else { '' }
    Write-Host ($status + ' ' + $name + $suffix)
}
function Run-Setup([string]$installDir, [string]$dataDir, [string]$tasks = '') {
    $arguments = @('/CURRENTUSER', '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        ('/DIR="' + $installDir + '"'), ('/DATADIR="' + $dataDir + '"'))
    if ($tasks) { $arguments += ('/TASKS="' + $tasks + '"') }
    $process = Start-Process -FilePath $Setup -ArgumentList $arguments -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw "setup failed with exit $($process.ExitCode)" }
}
function Run-Uninstall([string]$installDir, [bool]$removeData) {
    $uninstaller = Join-Path $installDir 'unins000.exe'
    if (-not (Test-Path $uninstaller)) { throw "uninstaller not found: $uninstaller" }
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    if ($removeData) { $arguments += '/REMOVEDATA=1' }
    $process = Start-Process -FilePath $uninstaller -ArgumentList $arguments -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw "uninstall failed with exit $($process.ExitCode)" }
    Start-Sleep -Seconds 2
}
try {
    if (Test-Path $Root) { Remove-Item $Root -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    Run-Setup $install $data 'desktopicon,startmenu'
    Check 'custom installation path with spaces' (Test-Path (Join-Path $install 'NL Code.exe')) $install
    Check 'embedded engine in selected path' (Test-Path (Join-Path $install 'engine\python\python.exe'))
    Check 'external data folder created' (Test-Path $data)
    Check 'extension installed in external data' (Test-Path (Join-Path $data 'extensions\nlcodingagent.nl-coding-agent-0.7.2\package.json'))
    Check 'portable profile not created in app folder' (-not (Test-Path (Join-Path $install 'data')))
    $config = Get-Content (Join-Path $install 'install-config.json') -Raw | ConvertFrom-Json
    Check 'configured data path recorded' ($config.dataDir -eq ($data -replace '\\', '/'))
    Check 'uninstall registered in Apps' ((Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' | ForEach-Object {
        $v = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        if ($v.DisplayName -like 'NL Code*' -and $v.InstallLocation -like ($install + '*')) { $true }
    }).Count -ge 1)
    Check 'desktop shortcut created' (Test-Path (Join-Path ([Environment]::GetFolderPath('Desktop')) 'NL Code.lnk'))
    $before = @(Get-Process -Name 'NL Code' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $cmd = Start-Process -FilePath "$env:WINDIR\System32\cmd.exe" -ArgumentList @('/c', ('start "" "' + (Join-Path $install 'NL Code Installed.cmd') + '" & ping -n 25 127.0.0.1 >nul')) -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 12
    $apps = @(Get-Process -Name 'NL Code' -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id })
    Check 'installed application launches' ($apps.Count -ge 1) (($apps | ForEach-Object { $_.Id }) -join ',')
    Check 'installed profile uses external data folder' (Test-Path (Join-Path $data 'user-data\User'))
    foreach ($app in $apps) { $app.CloseMainWindow() | Out-Null }
    Start-Sleep -Seconds 4
    if (-not $cmd.HasExited) { Stop-Process -Id $cmd.Id -Force -ErrorAction SilentlyContinue }
    foreach ($app in @(Get-Process -Name 'NL Code' -ErrorAction SilentlyContinue | Where-Object { $before -notcontains $_.Id })) {
        Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
    }
    Set-Content (Join-Path $data 'keep-on-uninstall.txt') 'keep' -Encoding ASCII
    Run-Setup $install $data 'startmenu'
    Check 'upgrade preserves data' ((Get-Content (Join-Path $data 'keep-on-uninstall.txt') -ErrorAction SilentlyContinue) -eq 'keep')
    Check 'upgrade preserves installation path' ((Get-Content (Join-Path $install 'install-config.json') -Raw | ConvertFrom-Json).installDir -eq ($install -replace '\\', '/'))
    Run-Uninstall $install $false
    Check 'uninstall removes application files' (-not (Test-Path (Join-Path $install 'NL Code.exe')))
    Check 'uninstall removes app folder' (-not (Test-Path $install))
    Check 'uninstall keeps personal data by default' (Test-Path $data)
    $remaining = @(Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' | Where-Object {
        $v = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        $v.DisplayName -like 'NL Code*'
    })
    Check 'uninstall removes Apps registration' ($remaining.Count -eq 0)
    Run-Setup $install $data ''
    Run-Uninstall $install $true
    Check 'explicit data removal deletes data folder' (-not (Test-Path $data))
    Check 'explicit data removal still removes app folder' (-not (Test-Path $install))
} finally {
    if (Test-Path $Root) { Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue }
}
$passed = @($results | Where-Object { -not $_.ok }).Count -eq 0
$report = [ordered]@{
    kind = 'windows-installer-lifecycle'
    date = (Get-Date).ToString('o')
    setup = $Setup
    createdWith = 'Inno Setup 6'
    root = $Root
    passed = $passed
    checks = $results
}
$evidence = Join-Path $repo '.workspace\evidence'
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$report | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $evidence 'windows-installer-verification.json') -Encoding UTF8
if (-not $passed) { throw 'Windows installer verification failed' }
Write-Host 'WINDOWS-INSTALLER-VERIFICATION-PASS'
