# Read-only NL Coding Agent external build inventory. Does not move/copy/delete anything.
# Paths are explicit user-reported K:\AI directories. No external process is modified.
$ErrorActionPreference = 'Stop'
$roots = @(
  'K:\AI\Coding Agent',
  'K:\AI\nl-coding-agent-portable',
  'K:\AI\nl-coding-agent-portable-clean',
  'K:\AI\nl-coding-agent-portable-final',
  'K:\AI\portable-smoke-project'
)
function Measure-TreeReadOnly([string]$root) {
  $size = [int64]0; $count = [int64]0; $skipped = [int64]0
  $relative = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
  $stack = [System.Collections.Generic.Stack[string]]::new()
  $stack.Push($root)
  while ($stack.Count -gt 0) {
    $dir = $stack.Pop()
    try { $entries = [System.IO.Directory]::EnumerateFileSystemEntries($dir) }
    catch { Write-Warning "Cannot read: $dir ($($_.Exception.Message))"; continue }
    foreach ($entry in $entries) {
      try {
        $attr = [System.IO.File]::GetAttributes($entry)
        if (($attr -band [IO.FileAttributes]::ReparsePoint) -ne 0) { $skipped++; continue }
        if (($attr -band [IO.FileAttributes]::Directory) -ne 0) { $stack.Push($entry) }
        else {
          $info = [System.IO.FileInfo]::new($entry)
          $size += $info.Length; $count++
          $rel = $entry.Substring($root.Length).TrimStart('\', '/')
          [void]$relative.Add($rel)
        }
      } catch { $skipped++; }
    }
  }
  return [PSCustomObject]@{ Root=$root; GB=[math]::Round(($size/1GB),3); Files=$count; SkippedEntries=$skipped; Relative=$relative }
}
$items = foreach ($p in $roots) {
  if (Test-Path -LiteralPath $p -PathType Container) { Measure-TreeReadOnly $p }
  else { Write-Warning "Missing directory: $p" }
}
$items | Select-Object Root,GB,Files,SkippedEntries | Format-Table -AutoSize
$portable = @($items | Where-Object { $_.Root -match 'nl-coding-agent-portable' })
if ($portable.Count -gt 1) {
  Write-Output '\nPortable relative-path overlaps (content NOT hash-verified):'
  foreach ($a in $portable) { foreach ($b in $portable) {
    if ([string]::Compare($a.Root,$b.Root,[StringComparison]::OrdinalIgnoreCase) -ge 0) { continue }
    $shared=0
    foreach ($key in $a.Relative) { if ($b.Relative.Contains($key)) { $shared++ } }
    Write-Output ("{0} vs {1}: shared names {2} ; only-left {3} ; only-right {4}" -f (Split-Path $a.Root -Leaf),(Split-Path $b.Root -Leaf),$shared,($a.Relative.Count-$shared),($b.Relative.Count-$shared))
  }}
}
Write-Output 'READ-ONLY AUDIT COMPLETE: no files changed. Matching names do NOT prove identical content.'
