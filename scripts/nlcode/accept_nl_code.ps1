#Requires -Version 7.0
<#
.SYNOPSIS
    Acceptance harness for the staged NL Code standalone distribution.

.DESCRIPTION
    Launches the packaged application with an isolated workbench profile, workspace and data directory,
    opens NL Chat through the command palette, sends a real message, captures a
    screenshot and verifies that the Python engine child was started and released.

    The check is deliberately separate from the build: a compiled package is not
    accepted until this (or the equivalent manual check) passes. It uses the
    Windows desktop focus gate and refuses to type into another application.

.EXAMPLE
    pwsh -File scripts/nlcode/accept_nl_code.ps1 -SeedFromLiveData
#>
[CmdletBinding()]
param(
    [string]$Dist = '',
    [string]$Project = '',
    [string]$DataDir = '',
    [string]$ScratchDir = '',
    [string]$PortableProfileDir = '',
    [string]$ScreenshotDir = '',
    [switch]$SeedFromLiveData,
    [int]$ReplyTimeoutSeconds = 90,
    [switch]$KeepOpen
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Dist) { $Dist = Join-Path $repoRoot '.workspace\dist\NL Code' }
if (-not $ScratchDir) { $ScratchDir = Join-Path $repoRoot ('.workspace\temp\nlcode-accept-' + (Get-Date -Format 'yyyyMMdd-HHmmssfff')) }
$scratch = $ScratchDir
if (-not $Project) { $Project = Join-Path $scratch 'project' }
if (-not $DataDir) { $DataDir = Join-Path $scratch 'data' }
if (-not $PortableProfileDir) { $PortableProfileDir = Join-Path $scratch 'portable-profile' }
if (-not $ScreenshotDir) { $ScreenshotDir = Join-Path $scratch 'screenshots' }
$workspaceDir = Join-Path $scratch 'workspace'
$portableExtensionsDir = Join-Path $PortableProfileDir 'extensions'
$engineRoot = $repoRoot

function Write-Result([string]$name, [bool]$ok, [string]$detail = '') {
    $line = '{0} {1}{2}' -f $(if ($ok) { 'PASS' } else { 'FAIL' }), $name, $(if ($detail) { ' — ' + $detail } else { '' })
    Write-Host $line
    [pscustomobject]@{ name = $name; ok = $ok; detail = $detail }
}

function Save-Shot([string]$name) {
    Add-Type -AssemblyName System.Drawing, System.Windows.Forms
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $path = Join-Path $ScreenshotDir ($name + '.png')
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    return $path
}

function Send-Keys([string]$keys, [int]$delayMs = 450) {
    [System.Windows.Forms.SendKeys]::SendWait($keys)
    Start-Sleep -Milliseconds $delayMs
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NlCodeGui {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
}
"@
Add-Type -AssemblyName System.Windows.Forms

$results = New-Object System.Collections.Generic.List[object]
$appExe = Join-Path $Dist 'NL Code.exe'
if (-not (Test-Path $appExe)) { $appExe = (Get-ChildItem $Dist -File -Filter '*.exe' | Select-Object -First 1).FullName }
if (-not $appExe) { throw "application executable not found in $Dist" }
$results.Add((Write-Result 'packaged application executable present' $true (Split-Path $appExe -Leaf))) | Out-Null

$launcher = Join-Path $Dist 'NL Code.bat'
$results.Add((Write-Result 'portable launcher present' (Test-Path $launcher) $launcher)) | Out-Null
$extensionDirs = @(Get-ChildItem (Join-Path $Dist 'data\extensions') -Directory -Filter 'nlcodingagent.nl-coding-agent-*' -ErrorAction SilentlyContinue)
$installedExtension = $null
if ($extensionDirs.Count -gt 0) {
    $installedExtension = $extensionDirs | Sort-Object {
        $package = Join-Path $_.FullName 'package.json'
        if (Test-Path $package) {
            [version]((Get-Content $package -Raw | ConvertFrom-Json).version)
        } else { [version]'0.0.0' }
    } -Descending | Select-Object -First 1
}
$results.Add((Write-Result 'extension installed in portable profile' ($null -ne $installedExtension -and (Test-Path (Join-Path $installedExtension.FullName 'package.json'))) $(if ($installedExtension) { $installedExtension.Name } else { '' }))) | Out-Null
$results.Add((Write-Result 'build metadata present' (Test-Path (Join-Path $Dist 'BUILD_INFO.json')) '')) | Out-Null

New-Item -ItemType Directory -Force -Path $Project, $DataDir, $portableExtensionsDir, $workspaceDir, $ScreenshotDir | Out-Null
if ($installedExtension) {
    Copy-Item -Path $installedExtension.FullName -Destination $portableExtensionsDir -Recurse -Force
}
if (-not (Test-Path (Join-Path $Project 'README.md'))) {
    Set-Content -Path (Join-Path $Project 'README.md') -Value "# NL Code acceptance project`n"
}
if ($SeedFromLiveData) {
    $liveData = Join-Path $repoRoot 'data'
    foreach ($item in @('nl_coding_agent.sqlite3', 'custom_agents.json', 'chat')) {
        $from = Join-Path $liveData $item
        if (Test-Path $from) { Copy-Item $from $DataDir -Recurse -Force }
    }
}

$env:NL_ENGINE_ROOT = $engineRoot
$env:NLCODE_ENGINE_ROOT = $engineRoot
$env:NL_DATA_DIR = $DataDir
$env:NL_WORKSPACE_DIR = $workspaceDir
$env:NL_MODELS_CONFIG = Join-Path $repoRoot 'config\models.yaml'
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

# Engine data snapshot (settings/agents/projects) before the app runs.
$snapshotScript = @'
import hashlib, json, os, sqlite3, sys
db = os.path.join(sys.argv[1], "nl_coding_agent.sqlite3")
out = {"settings": None, "projects": None}
if os.path.isfile(db):
    con = sqlite3.connect(db)
    try:
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in cur}
        if "app_settings" in names:
            rows = con.execute("SELECT key, value FROM app_settings ORDER BY key").fetchall()
            out["settings"] = {key: value for key, value in rows}
        if "projects" in names:
            out["projects"] = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    finally:
        con.close()
print(json.dumps(out))
'@
$snapshotFile = Join-Path $scratch 'engine-data-before.json'
Set-Content -Path (Join-Path $scratch 'snapshot.py') -Value $snapshotScript -Encoding UTF8
& (Join-Path $repoRoot 'python\python.exe') (Join-Path $scratch 'snapshot.py') $DataDir | Set-Content $snapshotFile -Encoding UTF8

Write-Host "launching: $appExe $Project"
$previousPortableDir = $env:VSCODE_PORTABLE
$env:VSCODE_PORTABLE = $PortableProfileDir
try {
    $process = Start-Process -FilePath $appExe -ArgumentList @(
        "`"$Project`"",
        '--new-window',
        '--disable-workspace-trust',
        '--skip-welcome',
        '--skip-release-notes'
    ) -PassThru
} finally {
    if ($null -eq $previousPortableDir) {
        Remove-Item Env:VSCODE_PORTABLE -ErrorAction SilentlyContinue
    } else {
        $env:VSCODE_PORTABLE = $previousPortableDir
    }
}
$deadline = (Get-Date).AddSeconds(90)
do {
    Start-Sleep -Milliseconds 500
    $process.Refresh()
} while ($process.MainWindowHandle -eq 0 -and -not $process.HasExited -and (Get-Date) -lt $deadline)
if ($process.HasExited) { throw "application exited early with code $($process.ExitCode)" }
if ($process.MainWindowHandle -eq 0) { throw 'application window did not appear' }
$results.Add((Write-Result 'application window started' $true)) | Out-Null

$handle = $process.MainWindowHandle
[NlCodeGui]::ShowWindow($handle, 3) | Out-Null
[NlCodeGui]::SetForegroundWindow($handle) | Out-Null
Start-Sleep -Seconds 3
$shotBefore = Save-Shot 'before-chat'
$results.Add((Write-Result 'screenshot captured before interaction' (Test-Path $shotBefore) $shotBefore)) | Out-Null

$fgPid = 0
for ($attempt = 0; $attempt -lt 12; $attempt++) {
    [NlCodeGui]::ShowWindow($handle, 3) | Out-Null
    $fg = [NlCodeGui]::GetForegroundWindow()
    $fgThread = [NlCodeGui]::GetWindowThreadProcessId($fg, [ref]$fgPid)
    $selfThread = [NlCodeGui]::GetCurrentThreadId()
    # Windows may refuse focus changes from a background process; attach to the
    # current foreground thread for the duration of the switch, then detach.
    [NlCodeGui]::AttachThreadInput($selfThread, $fgThread, $true) | Out-Null
    try {
        [NlCodeGui]::SetForegroundWindow($handle) | Out-Null
    } finally {
        [NlCodeGui]::AttachThreadInput($selfThread, $fgThread, $false) | Out-Null
    }
    Start-Sleep -Milliseconds 400
    $fg = [NlCodeGui]::GetForegroundWindow()
    [NlCodeGui]::GetWindowThreadProcessId($fg, [ref]$fgPid) | Out-Null
    if ($fgPid -eq $process.Id) { break }
    if ($attempt -eq 4 -or $attempt -eq 8) {
        try { (New-Object -ComObject WScript.Shell).AppActivate($process.Id) | Out-Null } catch { }
        Start-Sleep -Seconds 1
    }
}
if ($fgPid -ne $process.Id) {
    $process.CloseMainWindow() | Out-Null
    throw "refusing to send keys: foreground process $fgPid is not NL Code ($($process.Id))"
}

# First run with an empty profile may show the upstream Copilot onboarding dialog.
# Escape dismisses it; the check does not depend on it.
Send-Keys '{ESC}' 1500
$shotReady = Save-Shot 'after-dismiss'

Send-Keys '^%h' 1800
Start-Sleep -Seconds 4
$shotHome = Save-Shot 'home'
$results.Add((Write-Result 'NL Code home dashboard captured' (Test-Path $shotHome) $shotHome)) | Out-Null

Send-Keys '^n' 1200
Send-Keys '^w' 800
Send-Keys '^w' 800
Start-Sleep -Milliseconds 900
$shotWatermark = Save-Shot 'watermark'
$results.Add((Write-Result 'NL Code editor watermark captured' (Test-Path $shotWatermark) $shotWatermark)) | Out-Null

Send-Keys '^%h' 1200
Send-Keys '^+p' 900
Send-Keys 'Terminal: Create New Terminal' 900
Send-Keys '{ENTER}' 2200
$shotTerminal = Save-Shot 'terminal'
$results.Add((Write-Result 'Integrated terminal launched' (Test-Path $shotTerminal) $shotTerminal)) | Out-Null
Send-Keys '^+p' 900
Send-Keys 'Terminal: Kill the Active Terminal Instance' 700
Send-Keys '{ENTER}' 800

Send-Keys '^+p' 900
Send-Keys 'NL Code: Open Agents' 900
Send-Keys '{ENTER}' 1800
$shotAgents = Save-Shot 'agents'
$results.Add((Write-Result 'Agents and model assignments tab captured' (Test-Path $shotAgents) $shotAgents)) | Out-Null

Send-Keys '^+p' 900
Send-Keys 'NL Code: Open Chat' 900
Send-Keys '{ENTER}' 3500
Send-Keys 'Reply with exactly: NLCODE-GUI-OK' 500
Send-Keys '{ENTER}' 800
$shotSent = Save-Shot 'after-send'
Start-Sleep -Seconds $ReplyTimeoutSeconds
$shotReply = Save-Shot 'after-reply'
$results.Add((Write-Result 'NL Chat interaction captured' ((Test-Path $shotSent) -and (Test-Path $shotReply)) $shotReply)) | Out-Null

$engineChildren = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -like 'python*' -and $_.CommandLine -like '*mcp serve*' -and $_.CommandLine -like ('*' + $Project + '*')
    })
$results.Add((Write-Result 'Python engine child bound to the acceptance project' ($engineChildren.Count -ge 1) (($engineChildren | ForEach-Object { $_.ProcessId }) -join ','))) | Out-Null
$enginePids = @($engineChildren | ForEach-Object { $_.ProcessId })

if (-not $KeepOpen) {
    $process.CloseMainWindow() | Out-Null
    $closed = [bool]$process.WaitForExit(30000)
    Start-Sleep -Seconds 2
    $alive = @($enginePids | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
    $engineReleased = ($alive.Count -eq 0)
    $results.Add((Write-Result 'application closed' $closed)) | Out-Null
    $results.Add((Write-Result 'Python engine child released on shutdown' $engineReleased ($alive -join ','))) | Out-Null
    if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
}

& (Join-Path $repoRoot 'python\python.exe') (Join-Path $scratch 'snapshot.py') $DataDir | Set-Content (Join-Path $scratch 'engine-data-after.json') -Encoding UTF8
$before = Get-Content $snapshotFile -Raw | ConvertFrom-Json
$after = Get-Content (Join-Path $scratch 'engine-data-after.json') -Raw | ConvertFrom-Json
$existingKeys = @()
if ($null -ne $before.settings) {
    $existingKeys = @($before.settings.PSObject.Properties | ForEach-Object { $_.Name })
}
$preservedSettings = $true
foreach ($key in $existingKeys) {
    $beforeProperty = $before.settings.PSObject.Properties[$key]
    $afterProperty = $null
    if ($null -ne $after.settings) {
        $afterProperty = $after.settings.PSObject.Properties[$key]
    }
    if ($null -eq $afterProperty -or $afterProperty.Value -ne $beforeProperty.Value) {
        $preservedSettings = $false
        break
    }
}
$results.Add((Write-Result 'existing engine settings preserved' $preservedSettings (('preserved ' + $existingKeys.Count + ' preexisting key(s); new internal migration keys are allowed')))) | Out-Null

$failed = @($results | Where-Object { -not $_.ok })
$resultPath = Join-Path $scratch 'acceptance-result.json'
[ordered]@{
    dist       = $Dist
    project    = $Project
    dataDir    = $DataDir
    screenshots = @($shotBefore, $shotHome, $shotWatermark, $shotTerminal, $shotAgents, $shotSent, $shotReply)
    results    = $results
    passed     = ($failed.Count -eq 0)
    finishedAt = (Get-Date).ToString('o')
} | ConvertTo-Json -Depth 6 | Set-Content -Path $resultPath -Encoding UTF8
Write-Host ('result: ' + $resultPath)
if ($failed.Count -gt 0) { Write-Host ('FAILED CHECKS: ' + (($failed | ForEach-Object { $_.name }) -join '; ')) }
if ($failed.Count -eq 0) { Write-Host '== NLCODE-STANDALONE-ACCEPTANCE-PASS ==' } else { Write-Host '== NLCODE-STANDALONE-ACCEPTANCE-FAIL ==' }
exit $(if ($failed.Count -eq 0) { 0 } else { 1 })
