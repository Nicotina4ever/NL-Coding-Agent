# NL Code release assembly (local workspace only; artifacts are never committed).
# Produces the Windows portable package, the light setup bootstrap and the VSIX under
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
if (Test-Path $zipSource) {
    Copy-Item $zipSource $zip -Force
} else {
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path (Join-Path $payload '*') -DestinationPath $zip -CompressionLevel Fastest
}
$sha = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$size = (Get-Item $zip).Length
"$sha  NL-Code-Portable.zip" | Set-Content (Join-Path $windows 'NL-Code-Portable.zip.sha256') -Encoding ASCII

# Light installer: embeds only the checksum, release tag and bootstrapper logic.
$source = Get-Content (Join-Path $PSScriptRoot 'NLCodeSetup.cs') -Raw
$source = $source.Replace('__VERSION__', $Version).Replace('__RELEASE_TAG__', $ReleaseTag).Replace('__ZIP_SHA256__', $sha)
$setupSource = Join-Path $Releases 'NLCodeSetup.generated.cs'
Set-Content -Path $setupSource -Value $source -Encoding UTF8
$cscCandidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$csc = $cscCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $csc) { throw 'C# compiler not available for the setup bootstrap' }
$setupExe = Join-Path $windows 'NL-Code-Setup.exe'
& $csc /nologo /target:winexe "/out:$setupExe" /r:System.Windows.Forms.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Net.Http.dll $setupSource
if ($LASTEXITCODE -ne 0) { throw "setup bootstrap compilation failed: $LASTEXITCODE" }
Remove-Item $setupSource -Force

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
