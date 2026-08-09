#!/usr/bin/env bash
# /opt/mc/shutdown.sh — runs on the MC VPS via SSH from the controller.
#
# Ordered pipeline: SAVE → DOWN → SYNC → VERIFY. Exits non-zero at any step
# so the controller refuses to destroy the VPS. On exit 0, the controller
# does an independent S3 verification and only then calls DELETE /servers.
#
# Logs to /var/log/mc-shutdown.log AND stdout so the controller's SSH
# capture gets both.

set -euo pipefail

exec > >(tee -a /var/log/mc-shutdown.log) 2>&1
echo "=== shutdown.sh started at $(date -Is) ==="

# shellcheck disable=SC1091
source /opt/mc/s3.env

: "${TIER:?TIER not set}"
: "${HETZNER_S3_ENDPOINT:?}"
: "${HETZNER_S3_BUCKET:?}"
: "${HETZNER_S3_ACCESS_KEY:?}"
: "${HETZNER_S3_SECRET_KEY:?}"
: "${HETZNER_S3_WORLD_PREFIX:?}"

CONTAINER="mc-$TIER"
WORLD_DIR="/opt/mc/minecraft/data"

# ---- 1. Flush world to disk via RCON, then stop the container ----
if docker ps --format '{{.Names}}' | grep -Fxq "$CONTAINER"; then
    echo "Flushing world via RCON..."
    docker exec "$CONTAINER" rcon-cli save-all flush || {
        echo "WARN: save-all flush failed; continuing (world may be from last autosave)"
    }
    docker exec "$CONTAINER" rcon-cli save-off || true

    # Give MC a couple of seconds to actually finish writing.
    sleep 3

    echo "Stopping MC container..."
    cd /opt/mc
    docker compose --profile "$TIER" down
else
    echo "Container $CONTAINER not running; skipping RCON + docker compose down."
fi

# ---- 2. Sync world to Object Storage ----
if [ ! -d "$WORLD_DIR" ] || [ -z "$(ls -A "$WORLD_DIR" 2>/dev/null)" ]; then
    echo "ERROR: $WORLD_DIR is empty or missing. Refusing to sync empty world."
    exit 2
fi

export AWS_ACCESS_KEY_ID="$HETZNER_S3_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$HETZNER_S3_SECRET_KEY"
export AWS_DEFAULT_REGION="sgp1"

echo "Syncing world $WORLD_DIR to s3://${HETZNER_S3_BUCKET}/${HETZNER_S3_WORLD_PREFIX} ..."
aws --endpoint-url "$HETZNER_S3_ENDPOINT" \
    s3 sync "$WORLD_DIR/" "s3://${HETZNER_S3_BUCKET}/${HETZNER_S3_WORLD_PREFIX}" \
    --only-show-errors --delete

# ---- 3. Verify: count remote objects, count local files, compare ----
LOCAL=$(find "$WORLD_DIR" -type f | wc -l)
REMOTE=$(aws --endpoint-url "$HETZNER_S3_ENDPOINT" \
    s3 ls "s3://${HETZNER_S3_BUCKET}/${HETZNER_S3_WORLD_PREFIX}" --recursive \
    | wc -l)

echo "Local file count: $LOCAL"
echo "Remote object count: $REMOTE"

# The `--delete` on sync ensures we don't have stale objects. Local and
# remote should match exactly, but lock files may be excluded on some
# platforms — accept up to 2 file delta.
DELTA=$(( LOCAL > REMOTE ? LOCAL - REMOTE : REMOTE - LOCAL ))
if [ "$DELTA" -gt 2 ] || [ "$REMOTE" -lt 1 ]; then
    echo "ERROR: file-count mismatch (delta=$DELTA). Refusing to signal success."
    exit 3
fi

echo "=== shutdown.sh completed OK at $(date -Is) — synced $REMOTE objects. ==="
