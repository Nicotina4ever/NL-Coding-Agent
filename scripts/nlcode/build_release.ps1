# NL Code release assembly (local workspace only; artifacts are never committed).
# Produces the Windows portable package, the Inno Setup installer and the VSIX under
# .workspace/releases. macOS/Linux directories are created only to hold future verified
# artifacts; no placeholder binary is written.
[CmdletBinding()]
param(
    [string]$Dist = '',
    [string]$Releases = '',
    [string]$Version = '',
    [string]$ReleaseTag = ''
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Dist) { $Dist = Join-Path $repoRoot '.workspace\dist' }
if (-not $Releases) { $Releases = Join-Path $repoRoot '.workspace\releases' }
if (-not $Version) {
    $package = Get-Content (Join-Path $repoRoot 'frontend\package.json') -Raw | ConvertFrom-Json
    $Version = [string]$package.version
}
$payload = Join-Path $Dist 'NL Code'
if (-not $ReleaseTag) { $ReleaseTag = 'v' + $Version + '-beta.1' }
$vsixSource = Join-Path $Dist ('NL-Coding-Agent-' + $Version + '.vsix')
if (-not (Test-Path (Join-Path $payload 'NL Code.exe'))) { throw "standalone payload missing: $payload" }
if (-not (Test-Path (Join-Path $payload 'engine\python\python.exe'))) { throw 'embedded engine missing from payload' }
$extensionName = 'nlcodingagent.nl-coding-agent-' + $Version
$extensionRoot = Join-Path $payload ('data\extensions\' + $extensionName)
if (-not (Test-Path (Join-Path $extensionRoot 'package.json'))) { throw 'current extension missing from payload' }
$embedded = Get-Content (Join-Path $extensionRoot 'package.json') -Raw | ConvertFrom-Json
$info = Get-Content (Join-Path $payload 'BUILD_INFO.json') -Raw | ConvertFrom-Json
if ($embedded.version -ne $Version -or $info.extension -ne $extensionName) { throw 'payload version does not match requested release' }
if (-not (Test-Path $vsixSource)) { throw "package the current VSIX first: $vsixSource" }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$vsixArchive = [IO.Compression.ZipFile]::OpenRead($vsixSource)
try {
    $reader = [IO.StreamReader]::new($vsixArchive.GetEntry('extension/package.json').Open())
    try { $vsixPackage = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    if ($vsixPackage.version -ne $Version) { throw 'VSIX version mismatch' }
} finally { $vsixArchive.Dispose() }
if ((Test-Path $Releases) -and @(Get-ChildItem -LiteralPath $Releases -Force).Count) {
    throw "release output is not empty; preserve or stage the old release first: $Releases"
}

$windows = Join-Path $Releases 'windows'
$extension = Join-Path $Releases 'extension'
$macos = Join-Path $Releases 'macos'
$linux = Join-Path $Releases 'linux'
New-Item -ItemType Directory -Force -Path $windows, $extension, $macos, $linux | Out-Null

$zip = Join-Path $windows 'NL-Code-Portable.zip'
# Defaults come from tracked source, never from the live payload's mutable config.
$defaults = Join-Path (Split-Path $Releases -Parent) ('packaging-defaults-' + $Version)
if (Test-Path $defaults) { throw "packaging defaults directory already exists: $defaults" }
New-Item -ItemType Directory -Force -Path (Join-Path $defaults 'engine/config') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $defaults 'data/user-data/User') | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'default_settings.json') -Destination (Join-Path $defaults 'data/user-data/User/settings.json')
$defaultModels = Join-Path $defaults 'engine/config/models.yaml'
$trackedModels = & git -C $repoRoot show HEAD:config/models.yaml
if ($LASTEXITCODE -ne 0) { throw 'cannot read tracked model defaults' }
[IO.File]::WriteAllText($defaultModels, ($trackedModels -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
# Ship the extension itself, never its machine-specific index, user profiles,
# databases, runtime data, logs, shortcut paths or mutable engine configuration.
$archiveEntries = @(Get-ChildItem -LiteralPath $payload -Force | Where-Object {
    $_.Name -notin @('data', 'engine') -and $_.Extension -notin @('.log', '.lnk')
} | ForEach-Object { $_.Name })
$archiveEntries += @(Get-ChildItem -LiteralPath (Join-Path $payload 'engine') -Force | Where-Object {
    $_.Name -notin @('data', 'config')
} | ForEach-Object { 'engine/' + $_.Name })
$archiveEntries += 'data/extensions/' + $extensionName
$tar = Join-Path $env:WINDIR 'System32\tar.exe'
& $tar -a -c -f $zip --exclude '__pycache__' --exclude '*.pyc' --exclude '*.log' --exclude 'node-compile-cache' -C $payload @archiveEntries -C $defaults 'engine/config/models.yaml' 'data/user-data/User/settings.json'
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $zip)) {
    throw "portable archive creation failed: $LASTEXITCODE"
}
$sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$size = (Get-Item $zip).Length
"$sha  NL-Code-Portable.zip" | Set-Content (Join-Path $windows 'NL-Code-Portable.zip.sha256') -Encoding ASCII

# Standard Windows installer/uninstaller (Inno Setup). It ships the verified
# payload and lets the user choose install/data roots; the portable ZIP remains
# independent and self-contained.
$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 7\ISCC.exe')
)
$iscc = $isccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
if (-not $iscc) {
    throw 'Inno Setup (ISCC.exe) not found. Install it locally (winget install JRSoftware.InnoSetup) before building the standard installer.'
}
$setupExe = Join-Path $windows 'NL-Code-Setup.exe'
$iss = Join-Path $PSScriptRoot 'NLCode.iss'
$icon = Join-Path $payload 'resources\app\resources\win32\code.ico'
& $iscc "/DPayloadDir=$payload" "/DAppVersion=$Version" "/DModelsConfig=$defaultModels" "/DVsixFile=$vsixSource" "/DOutputDir=$windows" "/DSetupIcon=$icon" $iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed: $LASTEXITCODE" }
if (-not (Test-Path $setupExe)) { throw "installer not produced: $setupExe" }

if (-not (Test-Path $vsixSource)) {
    # A fresh BuildRoot/DistBase does not contain a VSIX yet; package it from the
    # already compiled frontend so a clean reconstruction remains complete.
    $frontend = Join-Path $repoRoot 'frontend'
    $vsce = Join-Path $frontend 'node_modules\.bin\vsce.cmd'
    if (-not (Test-Path $vsce)) { $vsce = Join-Path $frontend 'node_modules\.bin\vsce' }
    if (-not (Test-Path $vsce)) { throw "VSIX not found and vsce is unavailable: $vsixSource" }
    Push-Location $frontend
    try {
        & $vsce package --out $vsixSource
        if ($LASTEXITCODE -ne 0) { throw "VSIX packaging failed: $LASTEXITCODE" }
    } finally {
        Pop-Location
    }
}
if (Test-Path $vsixSource) {
    Copy-Item $vsixSource (Join-Path $extension 'NL-Coder.vsix') -Force
} elseif (Test-Path (Join-Path $extension 'NL-Coder.vsix')) {
    Write-Warning 'using the previously assembled VSIX; rebuild it with npm run package:vsix'
} else {
    throw "VSIX not found: $vsixSource"
}

$manifest = [ordered]@{
    version = $Version
    releaseTag = $ReleaseTag
    generatedAt = (Get-Date).ToString('o')
    windows = [ordered]@{
        status = 'built-awaiting-acceptance'
        portable = 'windows/NL-Code-Portable.zip'
        setup = 'windows/NL-Code-Setup.exe'
        installer = 'inno-setup'
        sha256 = $sha
        bytes = $size
    }
    extension = [ordered]@{ status = 'built'; path = 'extension/NL-Coder.vsix' }
    macos = [ordered]@{ status = 'not-built'; reason = 'requires a macOS runner and real validation' }
    linux = [ordered]@{ status = 'not-built'; reason = 'requires a Linux runner and real validation' }
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Releases 'release-manifest.json') -Encoding UTF8
Get-Item $zip, $setupExe, (Join-Path $extension 'NL-Coder.vsix') |
    Select-Object FullName, Length | Format-Table -AutoSize | Out-String | Write-Host
Write-Host ("Release assembled under " + $Releases)
