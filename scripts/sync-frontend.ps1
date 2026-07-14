param(
    [string]$Server = "162.251.93.73",
    [string]$User = "root",
    [int]$Port = 22,
    [string]$RemoteRoot = "/opt/comfy",
    [switch]$LocalBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $projectRoot "comfy-web"
$archive = Join-Path $env:TEMP "comfy-web-sync-$([guid]::NewGuid().ToString('N')).tar"
$remoteArchive = "$RemoteRoot/comfy-web-sync.tar"

if (-not (Test-Path -LiteralPath $frontend)) {
    throw "Frontend directory not found: $frontend"
}

try {
    if ($LocalBuild) {
        Push-Location $frontend
        try { npm run build } finally { Pop-Location }
    }

    Write-Host "Packaging frontend..."
    tar.exe -cf $archive -C $frontend --exclude=node_modules .
    if ($LASTEXITCODE -ne 0) { throw "Packaging failed." }

    Write-Host "Uploading frontend..."
    scp.exe -P $Port $archive "${User}@${Server}:$remoteArchive"
    if ($LASTEXITCODE -ne 0) { throw "Upload failed." }

    $remoteCommand = @"
set -eu
mkdir -p '$RemoteRoot/comfy-web'
rm -rf '$RemoteRoot/comfy-web'/*
tar -xf '$remoteArchive' -C '$RemoteRoot/comfy-web'
rm -f '$remoteArchive'
docker build --pull=false -t comfy-web-local:latest '$RemoteRoot/comfy-web'
docker rm -f comfy-comfy-web-1 2>/dev/null || true
docker run -d --name comfy-comfy-web-1 --restart unless-stopped --network comfy_default --network-alias comfy-web -p 80:80 comfy-web-local:latest
docker ps --filter name=comfy-comfy-web-1
"@

    Write-Host "Replacing frontend container only..."
    $remoteCommand | ssh.exe -p $Port "${User}@${Server}" "bash -s"
    if ($LASTEXITCODE -ne 0) {
        throw "Remote frontend sync failed. Exit code: $LASTEXITCODE"
    }

    Write-Host "Frontend sync completed. Backend containers were not restarted."
}
finally {
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
}
