# NL Code release assembly (local workspace only; artifacts are never committed).
# Produces the Windows portable package, the Inno Setup installer and the VSIX under
# .workspace/releases. macOS/Linux directories are created only to hold future verified
# artifacts; no placeholder binary is written.
[CmdletBinding()]
param(
    [string]$Dist = '',
    [string]$Releases = '',
    [string]$Version = '',
    [string]$ReleaseTag = 'v0.7.2-beta.1'
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
$zipSource = Join-Path $Dist 'NL-Code-0.7.2-portable-win64.zip'
$vsixSource = Join-Path $Dist ('NL-Coding-Agent-' + $Version + '.vsix')
if (-not (Test-Path (Join-Path $payload 'NL Code.exe'))) { throw "standalone payload missing: $payload" }
if (-not (Test-Path (Join-Path $payload 'engine\python\python.exe'))) { throw 'embedded engine missing from payload' }

$windows = Join-Path $Releases 'windows'
$extension = Join-Path $Releases 'extension'
$macos = Join-Path $Releases 'macos'
$linux = Join-Path $Releases 'linux'
New-Item -ItemType Directory -Force -Path $windows, $extension, $macos, $linux | Out-Null

$zip = Join-Path $windows 'NL-Code-Portable.zip'
# Build a clean portable ZIP from the verified payload, never including the
# machine/profile data/ directory. The portable launcher creates fresh local data.
$tar = Join-Path $env:WINDIR 'System32\tar.exe'
if (Test-Path $zip) { Remove-Item $zip -Force }
& $tar -a -c -f $zip --exclude 'data/*' -C $payload .
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
& $iscc "/DPayloadDir=$payload" "/DAppVersion=$Version" "/DOutputDir=$windows" "/DSetupIcon=$icon" $iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed: $LASTEXITCODE" }
if (-not (Test-Path $setupExe)) { throw "installer not produced: $setupExe" }

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
        status = 'verified-locally'
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
