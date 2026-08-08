# Gracefully stop the local Minecraft server.
#
# Usage:
#   .\scripts\stop.ps1 -Tier cpx21
#   .\scripts\stop.ps1 -Tier cpx31 -Backup     # copy world to ./minecraft/backup/<timestamp>/
#
# The -Backup flag mimics what the Phase 3 /stop-server command will do: copy
# the world folder to a backup location BEFORE tearing anything down, and
# verify the copy succeeded before removing the container. In Hetzner mode
# that copy step becomes an object-storage upload — same guard, different sink.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('cpx21', 'cpx31')]
    [string]$Tier,

    [switch]$Backup
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$container = "mc-$Tier"
$dataDir   = Join-Path $repoRoot 'minecraft\data'
$backupRoot = Join-Path $repoRoot 'minecraft\backup'

# 1. Ask the server to flush the world to disk via RCON. This uses `docker exec`
#    rather than an external RCON client so we don't need extra tools installed
#    just to stop the server.
$running = (docker ps --filter "name=^/${container}$" --format "{{.Names}}") -eq $container
if ($running) {
    Write-Host "Flushing world to disk via RCON (save-all flush)..." -ForegroundColor Cyan
    docker exec $container rcon-cli save-all flush | Out-Host
    docker exec $container rcon-cli save-off      | Out-Host
} else {
    Write-Host "Container $container is not running." -ForegroundColor Yellow
}

# 2. Optionally back up the world. MUST succeed before we tear the container down.
if ($Backup) {
    if (-not (Test-Path $dataDir)) {
        throw "World directory not found at $dataDir — nothing to back up."
    }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $target = Join-Path $backupRoot "$Tier-$stamp"
    Write-Host "Backing up world to $target ..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Copy-Item -Path (Join-Path $dataDir '*') -Destination $target -Recurse -Force

    # Verify: source and destination file counts should match.
    $srcCount = (Get-ChildItem -Recurse $dataDir | Measure-Object).Count
    $dstCount = (Get-ChildItem -Recurse $target  | Measure-Object).Count
    if ($srcCount -ne $dstCount) {
        throw "Backup verification failed: $srcCount source files vs $dstCount in backup. NOT stopping container."
    }
    Write-Host "Backup OK ($srcCount files)." -ForegroundColor Green
}

# 3. Stop and remove the container.
Write-Host "Stopping $container ..." -ForegroundColor Cyan
docker compose --profile $Tier down
Write-Host "Done." -ForegroundColor Green
