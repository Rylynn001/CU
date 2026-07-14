param(
    [int]$DebounceSeconds = 2
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$watchPath = Join-Path $projectRoot "comfy-web"
$syncScript = Join-Path $PSScriptRoot "sync-frontend.ps1"

$watcher = New-Object IO.FileSystemWatcher $watchPath
$watcher.IncludeSubdirectories = $true
$watcher.EnableRaisingEvents = $true
$watcher.Filter = "*"

$action = {
    $path = $Event.SourceEventArgs.FullPath
    if ($path -match "\\node_modules\\|\\dist\\|\.git\\") { return }
    Start-Sleep -Seconds $DebounceSeconds
    Write-Host "Change detected: $path"
    & $syncScript
}

$events = @(
    Register-ObjectEvent $watcher Changed -Action $action
    Register-ObjectEvent $watcher Created -Action $action
    Register-ObjectEvent $watcher Deleted -Action $action
    Register-ObjectEvent $watcher Renamed -Action $action
)

Write-Host "Watching $watchPath. Press Ctrl+C to stop."
try { while ($true) { Wait-Event -Timeout 1 | Out-Null } }
finally {
    $events | ForEach-Object { Unregister-Event -SourceIdentifier $_.Name -ErrorAction SilentlyContinue }
    $watcher.Dispose()
}
