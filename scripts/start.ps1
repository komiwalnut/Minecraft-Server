# Start the local Minecraft server under one of the resource-simulated tiers.
#
# Usage:
#   .\scripts\start.ps1 -Tier cpx21     # 3 vCPU / 4 GB
#   .\scripts\start.ps1 -Tier cpx31     # 4 vCPU / 8 GB
#   .\scripts\start.ps1 -Tier cpx21 -Follow
#
# Requires Docker Desktop running.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('cpx21', 'cpx31')]
    [string]$Tier,

    [switch]$Follow
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Ensure world-data directory exists so Docker doesn't create it as root.
$dataDir = Join-Path $repoRoot 'minecraft\data'
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir | Out-Null
    Write-Host "Created $dataDir"
}

Write-Host "Starting Minecraft server (tier: $Tier)..." -ForegroundColor Cyan
docker compose --profile $Tier up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed with exit $LASTEXITCODE" }

$container = "mc-$Tier"
Write-Host ""
Write-Host "Container: $container" -ForegroundColor Green
Write-Host "MC port  : localhost:25565"
Write-Host "RCON port: localhost:25575"
Write-Host ""
Write-Host "First boot downloads the server jar and generates the world (2-5 min)."
Write-Host "Watch progress: docker logs -f $container"

if ($Follow) {
    docker logs -f $container
}
