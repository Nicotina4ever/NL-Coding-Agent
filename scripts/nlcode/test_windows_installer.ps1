# Verifies the real Windows installer lifecycle: custom path with spaces, custom
# data root, launch, upgrade preserving path/settings, complete uninstall keeping
# personal data by default, and optional data removal.
[CmdletBinding()]
param(
    [string]$Setup = '',
    [string]$Root = '',
    [string]$PreviousSetup = ''
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Setup) { $Setup = Join-Path $repo '.workspace\releases\windows\NL-Code-Setup.exe' }
if (-not (Test-Path $Setup)) { throw "installer not found: $Setup" }
if (-not $Root) {
    # The legacy 0.7.2 setup is not long-path aware. Keep the fixture short so
    # its known MAX_PATH limitation cannot hide the actual upgrade behavior.
    $Root = Join-Path $repo ('.workspace\temp\i' + [guid]::NewGuid().ToString('N').Substring(0,4))
}
$Root = [IO.Path]::GetFullPath($Root)
$ownedTemp = [IO.Path]::GetFullPath((Join-Path $repo '.workspace/temp')) + [IO.Path]::DirectorySeparatorChar
if (-not $Root.StartsWith($ownedTemp, [StringComparison]::OrdinalIgnoreCase) -or (Test-Path -LiteralPath $Root)) {
    throw 'Use a new test directory inside the repository .workspace/temp.'
}
$appKey = '{A6C9E3D1-7B2C-4F0A-9D6E-52D8C5B4E7A1}_is1'
foreach ($hive in @('HKCU:', 'HKLM:')) {
    foreach ($key in @("$hive\Software\NL Code", "$hive\Software\Microsoft\Windows\CurrentVersion\Uninstall\$appKey")) {
        if (Test-Path -LiteralPath $key) { throw "Existing owner installation: use an isolated account instead of $key" }
    }
}
$version = (Get-Content (Join-Path $repo 'frontend/package.json') -Raw | ConvertFrom-Json).version
$install = Join-Path $Root 'A B'
$data = Join-Path $Root 'Data Folder'
$results = New-Object System.Collections.Generic.List[object]
function Check([string]$name, [bool]$ok, [string]$detail = '') {
    $results.Add([pscustomobject]@{ name = $name; ok = $ok; detail = $detail })
    $status = if ($ok) { 'PASS' } else { 'FAIL' }
    $suffix = if ($detail) { ' — ' + $detail } else { '' }
    Write-Host ($status + ' ' + $name + $suffix)
}
function Run-Setup([string]$installDir, [string]$dataDir, [string]$tasks = '', [string]$installer = $Setup) {
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        ('/DIR="' + $installDir + '"'), ('/DATADIR="' + $dataDir + '"'))
    $arguments += '/MERGETASKS="!desktopicon,!startmenu"'
    if ($PreviousSetup -and $installer -eq $PreviousSetup) { $arguments += '/CURRENTUSER' }
    $arguments += ('/LOG="' + (Join-Path $Root ('setup-' + $results.Count + '.log')) + '"')
    $process = Start-Process -FilePath $installer -ArgumentList $arguments -PassThru -Wait -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "setup failed with exit $($process.ExitCode)" }
}
function Run-Uninstall([string]$installDir, [bool]$removeData) {
    $uninstaller = Join-Path $installDir 'unins000.exe'
    if (-not (Test-Path $uninstaller)) { throw "uninstaller not found: $uninstaller" }
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    if ($removeData) { $arguments += '/REMOVEDATA=1' }
    $process = Start-Process -FilePath $uninstaller -ArgumentList $arguments -PassThru -Wait -WindowStyle Hidden
    if ($process.ExitCode -ne 0) { throw "uninstall failed with exit $($process.ExitCode)" }
    Start-Sleep -Seconds 2
}
$completed = $false
try {
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    # Silent installation must reject both overlap and junctions before writing
    # any app/data files or registration. All targets below belong to this fixture.
    $outside = Join-Path $Root 'Outside Target'
    New-Item -ItemType Directory -Path $outside | Out-Null
    Set-Content -LiteralPath (Join-Path $outside 'sentinel.txt') -Value 'keep' -Encoding ascii
    $badData = Join-Path $Root 'Junction Data'
    New-Item -ItemType Directory -Path $badData | Out-Null
    New-Item -ItemType Junction -Path (Join-Path $badData 'config') -Target $outside | Out-Null
    $badApp = Join-Path $Root 'Junction App'
    New-Item -ItemType Directory -Path $badApp | Out-Null
    New-Item -ItemType Junction -Path (Join-Path $badApp 'resources') -Target $outside | Out-Null
    foreach ($rejected in @(@($install, (Join-Path $install 'data')), @($install, $badData), @($badApp, $data))) {
        $args = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="'+$rejected[0]+'"'),('/DATADIR="'+$rejected[1]+'"'))
        $process = Start-Process -FilePath $Setup -ArgumentList $args -PassThru -Wait -WindowStyle Hidden
        Check 'unsafe or overlapping destination rejected before install' ($process.ExitCode -ne 0)
    }
    Check 'junction target was not written' (@(Get-ChildItem -LiteralPath $outside).Count -eq 1)
    Run-Setup $install $data '' $(if ($PreviousSetup) {$PreviousSetup} else {$Setup})
    Check 'custom installation path with spaces' (Test-Path (Join-Path $install 'NL Code.exe')) $install
    Check 'embedded engine in selected path' (Test-Path (Join-Path $install 'engine\python\python.exe'))
    Check 'external data folder created' (Test-Path $data)
    Check 'extension installed in external data' (@(Get-ChildItem (Join-Path $data 'extensions') -Directory -Filter 'nlcodingagent.nl-coding-agent-*').Count -ge 1)
    Check 'portable profile not created in app folder' (-not (Test-Path (Join-Path $install 'data')))
    $config = Get-Content (Join-Path $install 'install-config.json') -Raw | ConvertFrom-Json
    Check 'configured data path recorded' ($config.dataDir -eq ($data -replace '\\', '/'))
    Check 'uninstall registered in Apps' ((Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' | ForEach-Object {
        $v = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        if ($v.DisplayName -like 'NL Code*' -and $v.InstallLocation -like ($install + '*')) { $true }
    }).Count -ge 1)
    $initialModels = Get-Content -LiteralPath $config.modelsConfig -Raw
    $initialModels += "`n# acceptance-owner-model-preferences`n"
    Set-Content -LiteralPath $config.modelsConfig -Value $initialModels -NoNewline -Encoding utf8
    $before = @(Get-Process -Name 'NL Code' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $cmd = Start-Process -FilePath "$env:WINDIR\System32\cmd.exe" -ArgumentList @('/c', ('start "" "' + (Join-Path $install 'NL Code Installed.cmd') + '" & ping -n 25 127.0.0.1 >nul')) -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 12
    $appPath = Join-Path $install 'NL Code.exe'
    $apps = @(Get-Process -Name 'NL Code' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $appPath })
    Check 'installed application launches' ($apps.Count -ge 1) (($apps | ForEach-Object { $_.Id }) -join ',')
    Check 'installed profile uses external data folder' (Test-Path (Join-Path $data 'user-data\User'))
    foreach ($app in $apps) { $app.CloseMainWindow() | Out-Null }
    Start-Sleep -Seconds 4
    if (-not $cmd.HasExited) { Stop-Process -Id $cmd.Id -Force -ErrorAction SilentlyContinue }
    foreach ($app in @(Get-Process -Name 'NL Code' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $appPath })) {
        Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
    }
    Set-Content (Join-Path $data 'keep-on-uninstall.txt') 'keep' -Encoding ASCII
    $user = Join-Path $data 'user-data/User'
    New-Item -ItemType Directory -Force -Path $user | Out-Null
    Set-Content -LiteralPath (Join-Path $user 'settings.json') -Value '{"editor.fontSize":17}' -Encoding utf8
    $third = Join-Path $data 'extensions/acceptance.owner-1.0.0'
    New-Item -ItemType Directory -Force -Path $third | Out-Null
    Set-Content -LiteralPath (Join-Path $third 'package.json') -Value '{"name":"owner","publisher":"acceptance","version":"1.0.0","engines":{"vscode":"*"}}' -Encoding utf8
    Run-Setup $install $data 'startmenu'
    Check 'upgrade preserves data' ((Get-Content (Join-Path $data 'keep-on-uninstall.txt') -ErrorAction SilentlyContinue) -eq 'keep')
    Check 'upgrade preserves installation path' ((Get-Content (Join-Path $install 'install-config.json') -Raw | ConvertFrom-Json).installDir -eq ($install -replace '\\', '/'))
    $config = Get-Content (Join-Path $install 'install-config.json') -Raw | ConvertFrom-Json
    Check 'models migrated into writable data folder' ([IO.Path]::GetFullPath($config.modelsConfig) -eq [IO.Path]::GetFullPath((Join-Path $data 'config/models.yaml')))
    Check 'upgrade preserves model preferences' ((Get-Content -LiteralPath $config.modelsConfig -Raw).Contains('acceptance-owner-model-preferences'))
    Check 'upgrade preserves editor settings' ((Get-Content (Join-Path $user 'settings.json') -Raw | ConvertFrom-Json).'editor.fontSize' -eq 17)
    Check 'upgrade preserves other extensions' (Test-Path (Join-Path $third 'package.json'))
    Check 'current extension installed' (Test-Path (Join-Path $data ("extensions/nlcodingagent.nl-coding-agent-$version/package.json")))
    $index = Get-Content (Join-Path $data 'extensions/extensions.json') -Raw | ConvertFrom-Json
    Check 'extension index registers current version' (@($index | Where-Object {$_.identifier.id -eq 'nlcodingagent.nl-coding-agent' -and $_.version -eq $version}).Count -eq 1)
    # A junction added after installation must also block Inno's registered-file
    # removal, before the ordinary post-uninstall cleanup hook can run.
    $extensionPath = Join-Path $data ("extensions/nlcodingagent.nl-coding-agent-$version")
    $savedExtension = $extensionPath + '.fixture-saved'
    foreach ($ownedPath in @($extensionPath,$savedExtension)) {
        if (-not [IO.Path]::GetFullPath($ownedPath).StartsWith($Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'fixture path escapes test root' }
    }
    Move-Item -LiteralPath $extensionPath -Destination $savedExtension
    Set-Content -LiteralPath (Join-Path $outside 'package.json') -Value 'external-owner-sentinel' -Encoding ascii
    New-Item -ItemType Junction -Path $extensionPath -Target $outside | Out-Null
    $blockedUninstall = Start-Process -FilePath (Join-Path $install 'unins000.exe') -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -PassThru -Wait -WindowStyle Hidden
    Check 'uninstall rejects junction before registered file removal' ($blockedUninstall.ExitCode -ne 0)
    Check 'uninstall left junction target untouched' ((Get-Content -LiteralPath (Join-Path $outside 'package.json')).Trim() -eq 'external-owner-sentinel')
    if ((Get-Item -LiteralPath $extensionPath).LinkType -ne 'Junction') { throw 'expected test-owned junction' }
    Remove-Item -LiteralPath $extensionPath -Force
    Move-Item -LiteralPath $savedExtension -Destination $extensionPath
    Set-Content -LiteralPath (Join-Path $install 'resources/owner-added.txt') -Value 'owner' -Encoding ascii
    Run-Uninstall $install $false
    Check 'uninstall removes application files' (-not (Test-Path (Join-Path $install 'NL Code.exe')))
    Check 'uninstall preserves foreign app files' (Test-Path (Join-Path $install 'resources/owner-added.txt'))
    Check 'uninstall keeps personal data by default' (Test-Path $data)
    $remaining = @(Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' | Where-Object {
        $v = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        $v.InstallLocation -like ($install + '*')
    })
    Check 'uninstall removes Apps registration' ($remaining.Count -eq 0)
    $install = Join-Path $Root 'R B'
    $data = Join-Path $Root 'Removal Data'
    Run-Setup $install $data ''
    Check 'fresh data root has ownership marker' (Test-Path (Join-Path $data '.nl-code-data-owner'))
    Run-Uninstall $install $true
    Check 'explicit data removal deletes data folder' (-not (Test-Path $data))
    Check 'explicit data removal removes registered app files' (-not (Test-Path (Join-Path $install 'NL Code.exe')))
    $install = Join-Path $Root 'S B'
    $data = Join-Path $Root 'Shared Data'
    New-Item -ItemType Directory -Path $data | Out-Null
    Set-Content -LiteralPath (Join-Path $data 'unrelated.txt') -Value 'keep' -Encoding ascii
    Run-Setup $install $data ''
    Check 'pre-existing data directory is not claimed' (-not (Test-Path (Join-Path $data '.nl-code-data-owner')))
    Run-Uninstall $install $true
    Check 'explicit removal preserves unowned data' (Test-Path (Join-Path $data 'unrelated.txt'))
    $completed = $true
} finally {
    # Keep test evidence and any deliberately preserved owner fixtures for review.
    [ordered]@{setup=$Setup;previousSetup=$PreviousSetup;root=$Root;passed=($completed -and @($results | Where-Object {-not $_.ok}).Count -eq 0);checks=$results} |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $Root 'verification.json') -Encoding utf8
}
$passed = @($results | Where-Object { -not $_.ok }).Count -eq 0
$report = [ordered]@{
    kind = 'windows-installer-lifecycle'
    date = (Get-Date).ToString('o')
    setup = $Setup
    previousSetup = $PreviousSetup
    createdWith = 'Inno Setup 6'
    root = $Root
    passed = $passed
    checks = $results
}
$evidence = $Root
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$report | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $evidence 'verification.json') -Encoding UTF8
if (-not $passed) { throw 'Windows installer verification failed' }
Write-Host 'WINDOWS-INSTALLER-VERIFICATION-PASS'
