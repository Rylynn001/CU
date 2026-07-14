param(
    [string]$ComposeDir = (Split-Path -Parent $PSScriptRoot),
    [string]$Database = "comfyui"
)

$ErrorActionPreference = "Stop"
$schema = Join-Path $ComposeDir "database\schema.sql"

if (-not (Test-Path -LiteralPath $schema)) {
    throw "Schema file not found: $schema"
}

Push-Location $ComposeDir
try {
    docker compose cp $schema "mysql:/tmp/schema.sql"
    if ($LASTEXITCODE -ne 0) { throw "Failed to copy schema into MySQL container." }

    docker compose exec -T mysql sh -c "mysql -uroot -p`\"`$MYSQL_ROOT_PASSWORD`\" $Database < /tmp/schema.sql"
    if ($LASTEXITCODE -ne 0) { throw "Database initialization failed." }

    Write-Host "Database schema applied: $Database"
}
finally {
    Pop-Location
}
