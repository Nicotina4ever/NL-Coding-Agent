#Requires -Version 7.0
<#
.SYNOPSIS
    Build the NL Code standalone Windows distribution from the local Code - OSS
    checkout, reusing the existing NL Coding Engine installation.

.DESCRIPTION
    The build is reproducible and keeps every generated artifact under
    .workspace/build and .workspace/dist. The vendor checkout (vscode/) and the
    live engine data (data/) are never modified.

    Steps: copy source -> brand product.json + icons -> install deps -> build
    native modules against Electron headers -> compile -> package -> stage a
    portable distribution with the NL extension and the launcher.

    Two local workarounds for this machine are encoded explicitly and logged:
      * The repo preinstall script splits paths containing spaces; Electron
        headers are installed by calling node-gyp directly.
      * The installed MSVC toolchains lack the Spectre-mitigated libraries; the
        native binding.gyp files in the build tree are patched to build without
        them. Only the build tree is touched.

.EXAMPLE
    pwsh -File scripts/nlcode/build_nl_code.ps1 -ResyncSource
#>
[CmdletBinding()]
param(
    [string]$Source = '',
    [string]$BuildRoot = '',
    [string]$DistBase = '',
    [string]$NodeVersion = '24.22.1',
    [string]$NodeDir = '',
    [switch]$ResyncSource,
    [switch]$SkipDeps,
    [switch]$SkipNative,
    [switch]$SkipCompile,
    [switch]$SkipPackage,
    [switch]$SkipStage,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Source) { $Source = Join-Path $repoRoot 'vscode' }
if (-not $BuildRoot) { $BuildRoot = Join-Path $repoRoot '.workspace\build\nl-code-oss' }
if (-not $DistBase) { $DistBase = Join-Path $repoRoot '.workspace\dist' }
$src = Join-Path $BuildRoot 'src'
$packageDir = Join-Path $BuildRoot 'VSCode-win32-x64'
$distName = 'NL Code'
$dist = Join-Path $DistBase $distName
$logDir = $BuildRoot
$brandNameShort = 'NL Code'

function Write-Step([string]$text) {
    Write-Host ''
    Write-Host ('=== ' + $text) -ForegroundColor Cyan
}

function Invoke-Native([string]$file, [string[]]$arguments, [string]$workingDirectory) {
    Push-Location $workingDirectory
    try {
        & $file @arguments
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($code -ne 0) {
        throw ("command failed ({0}): {1} {2}" -f $code, $file, ($arguments -join ' '))
    }
}

# ---------------------------------------------------------------- prerequisites
if (-not (Test-Path (Join-Path $Source 'package.json'))) { throw "Code - OSS source not found: $Source" }
if (-not (Test-Path (Join-Path $Source 'product.json'))) { throw "product.json not found in $Source" }
$python = Join-Path $repoRoot 'python\python.exe'
if (-not (Test-Path $python)) { throw "embedded python not found: $python" }
if (-not $NodeDir) {
    $NodeDir = Join-Path $repoRoot ('.workspace\tools\node-v' + $NodeVersion + '-win-x64')
}
if (-not (Test-Path (Join-Path $NodeDir 'node.exe'))) {
    Write-Step "Download Node.js $NodeVersion (portable, repository-local)"
    $tools = Join-Path $repoRoot '.workspace\tools'
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    $zip = Join-Path $tools ("node-v$NodeVersion-win-x64.zip")
    if (-not (Test-Path $zip) -or $Force) {
        Invoke-WebRequest -Uri ("https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip") -OutFile $zip -UseBasicParsing
    }
    Expand-Archive -Path $zip -DestinationPath $tools -Force
}
$env:PATH = "$NodeDir;$env:PATH"
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$npm = Join-Path $NodeDir 'npm.cmd'
Write-Host ("node: " + (& (Join-Path $NodeDir 'node.exe') --version) + "  npm: " + (& $npm --version))

New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null

# ------------------------------------------------------------------ source copy
if ($ResyncSource -or $Force -or -not (Test-Path (Join-Path $src 'package.json'))) {
    Write-Step "Copy Code - OSS source to $src (vendor checkout stays untouched)"
    if (-not $src.StartsWith($BuildRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'unsafe build source path' }
    if (Test-Path $src) { Remove-Item -Recurse -Force $src }
    robocopy $Source $src /MIR /XD .git /NFL /NDL /NJH /NJS /NP /R:2 /W:2 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }
}

# ---------------------------------------------------------------------- branding
Write-Step 'Apply NL Code product branding and icons'
$productPath = Join-Path $src 'product.json'
$backupPath = Join-Path $src 'product.original.json'
if (-not (Test-Path $backupPath)) { Copy-Item $productPath $backupPath }
$product = Get-Content $productPath -Raw | ConvertFrom-Json
$branding = [ordered]@{
    nameShort            = $brandNameShort
    nameLong             = 'NL Code'
    applicationName      = 'nl-code'
    dataFolderName       = '.nl-code'
    sharedDataFolderName = '.nl-code-shared'
    win32DirName         = 'NL Code'
    win32NameVersion     = 'NL Code'
    win32RegValueName    = 'NLCode'
    win32AppUserModelId  = 'NL.Code'
    win32ShellNameShort  = 'NL Code'
    win32MutexName       = 'nlcode'
    urlProtocol          = 'nl-code'
}
foreach ($key in $branding.Keys) {
    $product | Add-Member -NotePropertyName $key -NotePropertyValue $branding[$key] -Force
}
# Upstream Insiders product keeps defaultChatAgent/trustedExtensionAuthAccess; the workbench
# agent host in 1.145 needs them to render. The first-run Copilot onboarding dialog is a
# one-time upstream behaviour (the acceptance harness presses Escape); NL Chat is independent.
$product | ConvertTo-Json -Depth 100 | Set-Content -Path $productPath -Encoding UTF8
Invoke-Native $python @((Join-Path $PSScriptRoot 'make_brand_icon.py'), (Join-Path $src 'resources\win32')) $repoRoot

Write-Step 'Replace the editor watermark with the NL Code identity'
$watermarkMedia = Join-Path $src 'src\vs\workbench\browser\parts\editor\media'
$watermarkMap = @{
    'nl-watermark-light.svg'   = 'letterpress-light.svg'
    'nl-watermark-dark.svg'    = 'letterpress-dark.svg'
    'nl-watermark-hcLight.svg' = 'letterpress-hcLight.svg'
    'nl-watermark-hcDark.svg'  = 'letterpress-hcDark.svg'
}
foreach ($sourceName in $watermarkMap.Keys) {
    $source = Join-Path $repoRoot ('assets\' + $sourceName)
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $watermarkMedia $watermarkMap[$sourceName]) -Force
    }
}

# ------------------------------------------------------------------ dependencies
if (-not $SkipDeps) {
    Write-Step 'Install dependencies (scripts skipped; native modules are built explicitly)'
    Invoke-Native $npm @('ci', '--ignore-scripts') $src
}

# Electron headers (preinstall.ts cannot run because it does not quote spaces).
Write-Step 'Install Electron 43.8.3 headers'
$gyp = Join-Path $src 'build\npm\gyp\node_modules\.bin\node-gyp.cmd'
if (-not (Test-Path $gyp)) {
    Invoke-Native $npm @('ci') (Join-Path $src 'build\npm\gyp')
}
Invoke-Native $gyp @('install', '--dist-url', 'https://electronjs.org/headers', '43.8.3') $src

# Local Spectre workaround: inject the property as false instead of "Spectre".
Write-Step 'Patch binding.gyp Spectre flags in the build tree only'
$patched = 0
Get-ChildItem (Join-Path $src 'node_modules') -Recurse -File -Include '*.gyp', '*.gypi' -ErrorAction SilentlyContinue | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    if ($content -match 'SpectreMitigation') {
        $updated = $content.Replace('"SpectreMitigation": "Spectre"', '"SpectreMitigation": "false"').Replace("'SpectreMitigation': 'Spectre'", "'SpectreMitigation': 'false'")
        if ($updated -ne $content) {
            Set-Content -Path $_.FullName -Value $updated -NoNewline -Encoding UTF8
            $script:patched++
        }
    }
}
Write-Host ("patched gyp files: " + $patched)

# ------------------------------------------------------------------ native build
if (-not $SkipNative) {
    Write-Step 'Build native modules against Electron headers'
    $env:npm_config_target = '43.8.3'
    $env:npm_config_runtime = 'electron'
    $env:npm_config_disturl = 'https://electronjs.org/headers'
    $env:npm_config_ms_build_id = '15784459'
    $knownOptional = @('node_modules\cpu-features', 'node_modules\ssh2\lib\protocol\crypto')
    $nativeDirs = Get-ChildItem (Join-Path $src 'node_modules') -Recurse -Filter 'binding.gyp' -File -ErrorAction SilentlyContinue |
        ForEach-Object { $_.DirectoryName } | Sort-Object -Unique
    $failures = @()
    foreach ($dir in $nativeDirs) {
        $relative = $dir.Replace($src + '\', '')
        Push-Location $dir
        try { & $gyp rebuild *> (Join-Path $logDir ('native-' + ($relative -replace '[\\/]', '_') + '.log')) }
        finally { Pop-Location }
        $code = $LASTEXITCODE
        if ($code -ne 0) {
            if ($knownOptional -contains $relative) {
                Write-Host ("  optional module not built: " + $relative) -ForegroundColor Yellow
            } else {
                $failures += $relative
            }
        } else {
            Write-Host ("  ok " + $relative)
        }
    }
    if ($failures.Count -gt 0) { throw ("native modules failed: " + ($failures -join ', ')) }
}

# ------------------------------------------------------------------ extensions
if (-not $SkipCompile) {
    Write-Step 'Install build and built-in extension dependencies (scripts disabled)'
    $targets = New-Object System.Collections.Generic.List[string]
    $buildDir = Join-Path $src 'build'
    if (Test-Path (Join-Path $buildDir 'package.json')) { $targets.Add($buildDir) | Out-Null }
    $extRoot = Join-Path $src 'extensions'
    if (Test-Path (Join-Path $extRoot 'package.json')) { $targets.Add($extRoot) | Out-Null }
    Get-ChildItem $extRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        if (Test-Path (Join-Path $_.FullName 'package.json')) { $targets.Add($_.FullName) | Out-Null }
        $server = Join-Path $_.FullName 'server'
        if (Test-Path (Join-Path $server 'package.json')) { $targets.Add($server) | Out-Null }
    }
    # Selfhost development extensions are typechecked by the compile task.
    $selfhostRoot = Join-Path $src '.vscode\extensions'
    Get-ChildItem $selfhostRoot -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        if (Test-Path (Join-Path $_.FullName 'package.json')) { $targets.Add($_.FullName) | Out-Null }
    }
    $installTargets = $targets | Sort-Object -Unique
    $npmLocal = $npm
    $installResults = $installTargets | ForEach-Object -Parallel {
        $dir = $_
        $hasLock = Test-Path (Join-Path $dir 'package-lock.json')
        $installArgs = if ($hasLock) { @('ci', '--ignore-scripts', '--no-audit', '--no-fund') } else { @('install', '--ignore-scripts', '--no-audit', '--no-fund') }
        Push-Location $dir
        try { & $using:npmLocal @installArgs *> (Join-Path $dir 'nlcode-install.log'); $code = $LASTEXITCODE }
        finally { Pop-Location }
        [pscustomobject]@{ dir = $dir; exit = $code }
    } -ThrottleLimit 6
    $installFailures = @($installResults | Where-Object { $_.exit -ne 0 })
    if ($installFailures.Count -gt 0) {
        throw ('extension dependency install failed: ' + (($installFailures | ForEach-Object { $_.dir }) -join ', '))
    }

    Write-Step 'Compile client and built-in extensions'
    Invoke-Native $npm @('run', 'gulp', 'compile') $src
}

# --------------------------------------------------------------------- package
if (-not $SkipPackage) {
    Write-Step 'Package the Windows x64 application (minified)'
    # Cross-platform native prebuilds are not PE files; the Windows packaging task
    # would try to rcedit them and abort. Remove non-Windows prebuilds from the build tree.
    Get-ChildItem (Join-Path $src 'node_modules') -Recurse -Directory -Filter 'prebuilds' -ErrorAction SilentlyContinue | ForEach-Object {
        Get-ChildItem $_.FullName -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^(linux|darwin|alpine|android|freebsd)' } |
            ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    }
    # The Copilot SDK is not bundled in this local build, so the upstream post-package
    # ripgrep-shim task would fail after the application is already fully packaged.
    # Skip that task in the build tree; NL Chat and the editor are unaffected.
    $vscodeGulp = Join-Path $src 'build\gulpfile.vscode.ts'
    $gulpContent = Get-Content $vscodeGulp -Raw
    $shimPattern = [regex]'(packageTask\(platform, arch, sourceFolderName, destinationFolderName, opts\),)\s*\r?\n\s*prepareCopilotRipgrepShimTask\(platform, arch, destinationFolderName\)'
    if ($shimPattern.IsMatch($gulpContent)) {
        $gulpContent = $shimPattern.Replace($gulpContent, '$1', 1)
        Set-Content -Path $vscodeGulp -Value $gulpContent -Encoding UTF8
        Write-Host 'patched build tree: Copilot ripgrep shim task skipped'
    } elseif ($gulpContent.Contains('prepareCopilotRipgrepShimTask(platform, arch, destinationFolderName)')) {
        throw 'unexpected gulpfile shape: cannot neutralise the Copilot ripgrep shim task'
    } else {
        Write-Host 'build tree already has the Copilot ripgrep shim task disabled'
    }
    if (-not $env:VSCODE_QUALITY) { $env:VSCODE_QUALITY = 'stable' }
    # The Windows packaging task verifies Authenticode signatures; signtool lives in the SDK.
    $signtool = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe' -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($signtool) { $env:PATH = $signtool.DirectoryName + ';' + $env:PATH }
    if (-not $env:BUILD_SOURCEVERSION) {
        $commit = (& git -C $Source rev-parse HEAD 2>$null)
        if ($commit) { $env:BUILD_SOURCEVERSION = $commit.Trim() }
    }
    Invoke-Native $npm @('run', 'gulp', 'vscode-win32-x64-min') $src
    if (-not (Test-Path $packageDir)) { throw "package output not found: $packageDir" }
}

if ($SkipStage) {
    Write-Host ''
    Write-Host ("Packaged application: " + $packageDir) -ForegroundColor Green
    exit 0
}

# ------------------------------------------------------------------------ stage
Write-Step "Stage portable distribution: $dist"
if (-not (Test-Path $packageDir)) { throw "package output not found: $packageDir (use -SkipPackage only after a build)" }
$distBaseResolved = (Resolve-Path $DistBase).Path
if (-not $dist.StartsWith($distBaseResolved, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'unsafe dist path' }
if (Test-Path $dist) { Remove-Item -Recurse -Force $dist }
robocopy $packageDir $dist /E /NFL /NDL /NJH /NJS /NP /R:2 /W:2 | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed: $LASTEXITCODE" }

$appExe = Join-Path $dist ($brandNameShort + '.exe')
if (-not (Test-Path $appExe)) {
    $candidate = Get-ChildItem $dist -File -Filter '*.exe' | Select-Object -First 1
    if (-not $candidate) { throw 'application executable not found in dist' }
    $appExe = $candidate.FullName
}
$appExeName = Split-Path $appExe -Leaf

Write-Step 'Apply the NL Code watermark to the packaged workbench assets'
$watermarkTargets = @(
    (Join-Path $dist 'resources\app\out\media'),
    (Join-Path $dist 'resources\app\out\vs\workbench\browser\parts\editor\media')
)
foreach ($target in $watermarkTargets) {
    if (-not (Test-Path $target)) { continue }
    Copy-Item (Join-Path $repoRoot 'assets\nl-watermark-light.svg') (Join-Path $target 'letterpress-light.svg') -Force
    Copy-Item (Join-Path $repoRoot 'assets\nl-watermark-dark.svg') (Join-Path $target 'letterpress-dark.svg') -Force
    Copy-Item (Join-Path $repoRoot 'assets\nl-watermark-hcLight.svg') (Join-Path $target 'letterpress-hcLight.svg') -Force
    Copy-Item (Join-Path $repoRoot 'assets\nl-watermark-hcDark.svg') (Join-Path $target 'letterpress-hcDark.svg') -Force
}

Write-Step 'Build and install the NL Coding Agent extension into the portable profile'
$frontend = Join-Path $repoRoot 'frontend'
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) { Invoke-Native $npm @('install') $frontend }
Invoke-Native $npm @('run', 'compile') $frontend
$extPackage = Get-Content (Join-Path $frontend 'package.json') -Raw | ConvertFrom-Json
$extDirName = $extPackage.publisher + '.' + $extPackage.name + '-' + $extPackage.version
$extTarget = Join-Path $dist ('data\extensions\' + $extDirName)
New-Item -ItemType Directory -Force -Path $extTarget | Out-Null
foreach ($item in @('package.json', 'package-lock.json', 'out', 'media', 'assets', 'themes')) {
    $from = Join-Path $frontend $item
    if (Test-Path $from) { Copy-Item $from (Join-Path $extTarget $item) -Recurse -Force }
}
Invoke-Native $npm @('ci', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund') $extTarget

Write-Step 'Seed NL Code default profile settings (existing user settings are preserved)'
$userDir = Join-Path $dist 'data\user-data\User'
New-Item -ItemType Directory -Force -Path $userDir | Out-Null
$settingsPath = Join-Path $userDir 'settings.json'
if (-not (Test-Path $settingsPath)) {
    [ordered]@{
        'workbench.colorTheme'            = 'NL Code Dark'
        'workbench.startupEditor'         = 'none'
        'workbench.tips.enabled'          = $false
        'workbench.activityBar.location'  = 'top'
        'workbench.layoutControl.enabled' = $true
        'workbench.secondarySideBar.defaultVisibility' = 'visibleInWorkspace'
        'window.commandCenter'            = $true
        'explorer.compactFolders'         = $false
        'chat.disableAIFeatures'          = $true
        'telemetry.telemetryLevel'        = 'off'
    } | ConvertTo-Json -Depth 5 | Set-Content -Path $settingsPath -Encoding UTF8
}

Write-Step 'Write launcher and build metadata'
$launcherTemplate = Get-Content (Join-Path $PSScriptRoot 'launcher.bat') -Raw
$launcher = $launcherTemplate.Replace('__ENGINE_ROOT__', $repoRoot).Replace('__APP_EXE__', $appExeName)
Set-Content -Path (Join-Path $dist 'NL Code.bat') -Value $launcher -Encoding ASCII
$commitInfo = (& git -C $Source rev-parse HEAD 2>$null)
if ($commitInfo) { $commitInfo = $commitInfo.Trim() }
$buildInfo = [ordered]@{
    product           = 'NL Code'
    appExecutable     = $appExeName
    codeOssVersion    = (Get-Content (Join-Path $src 'package.json') -Raw | ConvertFrom-Json).version
    codeOssCommit     = $commitInfo
    engineRoot        = $repoRoot
    extension         = $extDirName
    node              = (& (Join-Path $NodeDir 'node.exe') --version)
    builtAt           = (Get-Date).ToString('o')
    portableProfile   = 'data\user-data + data\extensions'
    spectreWorkaround = 'binding.gyp SpectreMitigation disabled in the build tree (no Spectre libs installed)'
    optionalNativeNotBuilt = @('cpu-features', 'ssh2 crypto (pure-JS fallback)')
}
$buildInfo | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $dist 'BUILD_INFO.json') -Encoding UTF8
if (Test-Path (Join-Path $repoRoot 'docs\NL_CODE_STANDALONE.md')) {
    Copy-Item (Join-Path $repoRoot 'docs\NL_CODE_STANDALONE.md') (Join-Path $dist 'README-NL-CODE.md') -Force
}

Write-Host ''
Write-Host ("NL Code staged: " + $dist) -ForegroundColor Green
Write-Host ("Launcher: " + (Join-Path $dist 'NL Code.bat'))
Write-Host ("Engine:   " + $repoRoot)
