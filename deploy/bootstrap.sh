#!/usr/bin/env bash
# /opt/mc/bootstrap.sh — runs on VPS first boot via cloud-init.
#
# Reads S3 creds + tier from /opt/mc/s3.env (written by cloud-init user-data),
# syncs the latest world from Hetzner Object Storage, then starts the MC
# container via docker compose.
#
# Logs to /var/log/mc-bootstrap.log for post-mortem debugging.

set -euo pipefail

exec > >(tee -a /var/log/mc-bootstrap.log) 2>&1
echo "=== bootstrap.sh started at $(date -Is) ==="

# shellcheck disable=SC1091
source /opt/mc/s3.env

# Sanity-check the required vars.
: "${TIER:?TIER not set in /opt/mc/s3.env}"
: "${HETZNER_S3_ENDPOINT:?}"
: "${HETZNER_S3_BUCKET:?}"
: "${HETZNER_S3_ACCESS_KEY:?}"
: "${HETZNER_S3_SECRET_KEY:?}"
: "${HETZNER_S3_WORLD_PREFIX:?}"
: "${RCON_PASSWORD:?}"

# Ensure awscli is available. On first boot from a fresh snapshot it should
# already be present (it's installed during the base-VPS build), but be
# defensive.
if ! command -v aws >/dev/null 2>&1; then
    echo "awscli not found; installing..."
    apt-get update -y
    apt-get install -y awscli
fi

# Export creds for the aws CLI.
export AWS_ACCESS_KEY_ID="$HETZNER_S3_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$HETZNER_S3_SECRET_KEY"
export AWS_DEFAULT_REGION="sgp1"

WORLD_DIR="/opt/mc/minecraft/data"
mkdir -p "$WORLD_DIR"

# Pull the latest world from Object Storage. If the prefix is empty (first
# ever run, no world uploaded yet), aws s3 sync exits 0 with no files copied
# — MC will generate a fresh world when the container starts.
echo "Syncing world from s3://${HETZNER_S3_BUCKET}/${HETZNER_S3_WORLD_PREFIX} to $WORLD_DIR ..."
aws --endpoint-url "$HETZNER_S3_ENDPOINT" \
    s3 sync "s3://${HETZNER_S3_BUCKET}/${HETZNER_S3_WORLD_PREFIX}" "$WORLD_DIR/" \
    --only-show-errors

echo "Setting ownership on world dir (itzg image runs as uid 1000)..."
chown -R 1000:1000 "$WORLD_DIR"

# Pass RCON_PASSWORD to docker-compose via the environment. docker-compose.yml
# reads it via ${RCON_PASSWORD:-default}.
export RCON_PASSWORD

echo "Starting MC container (profile: $TIER) ..."
cd /opt/mc
docker compose --profile "$TIER" up -d

echo "=== bootstrap.sh finished at $(date -Is) ==="
