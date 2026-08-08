#!/usr/bin/env bash
# Linux mirror of stop.ps1.
# Usage: ./scripts/stop.sh cpx21 [--backup]
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <cpx21|cpx31> [--backup]" >&2
    exit 2
fi

TIER="$1"
DO_BACKUP="${2:-}"

case "$TIER" in
    cpx21|cpx31) ;;
    *) echo "Tier must be cpx21 or cpx31, got: $TIER" >&2; exit 2 ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

CONTAINER="mc-$TIER"
DATA_DIR="$REPO_ROOT/minecraft/data"
BACKUP_ROOT="$REPO_ROOT/minecraft/backup"

if docker ps --filter "name=^/${CONTAINER}$" --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "Flushing world to disk via RCON..."
    docker exec "$CONTAINER" rcon-cli save-all flush
    docker exec "$CONTAINER" rcon-cli save-off
else
    echo "Container $CONTAINER is not running."
fi

if [[ "$DO_BACKUP" == "--backup" ]]; then
    if [[ ! -d "$DATA_DIR" ]]; then
        echo "World directory not found at $DATA_DIR — nothing to back up." >&2
        exit 1
    fi
    STAMP=$(date +%Y%m%d-%H%M%S)
    TARGET="$BACKUP_ROOT/$TIER-$STAMP"
    echo "Backing up world to $TARGET ..."
    mkdir -p "$TARGET"
    cp -a "$DATA_DIR/." "$TARGET/"

    SRC_COUNT=$(find "$DATA_DIR" -type f | wc -l)
    DST_COUNT=$(find "$TARGET"   -type f | wc -l)
    if [[ "$SRC_COUNT" -ne "$DST_COUNT" ]]; then
        echo "Backup verification failed: $SRC_COUNT source vs $DST_COUNT in backup. NOT stopping." >&2
        exit 1
    fi
    echo "Backup OK ($SRC_COUNT files)."
fi

echo "Stopping $CONTAINER ..."
docker compose --profile "$TIER" down
echo "Done."
