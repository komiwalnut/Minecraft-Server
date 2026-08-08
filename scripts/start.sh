#!/usr/bin/env bash
# Linux mirror of start.ps1 — same behavior, POSIX shell.
# Usage: ./scripts/start.sh cpx21 [--follow]
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <cpx21|cpx31> [--follow]" >&2
    exit 2
fi

TIER="$1"
FOLLOW="${2:-}"

case "$TIER" in
    cpx21|cpx31) ;;
    *) echo "Tier must be cpx21 or cpx31, got: $TIER" >&2; exit 2 ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p minecraft/data

echo "Starting Minecraft server (tier: $TIER)..."
docker compose --profile "$TIER" up -d

CONTAINER="mc-$TIER"
echo
echo "Container: $CONTAINER"
echo "MC port  : localhost:25565"
echo "RCON port: localhost:25575"
echo
echo "First boot downloads the server jar and generates the world (2-5 min)."
echo "Watch progress: docker logs -f $CONTAINER"

if [[ "$FOLLOW" == "--follow" ]]; then
    exec docker logs -f "$CONTAINER"
fi
