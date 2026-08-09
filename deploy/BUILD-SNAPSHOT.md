# Building the MC-VPS snapshot

One-time recipe. The result is a Hetzner snapshot ID you put in `.env` as `HETZNER_SNAPSHOT_ID`. Every future `/start-server` boots from this snapshot; the snapshot itself is never modified.

The snapshot needs:
- Ubuntu 24.04 with Docker Engine
- `/opt/mc/` = this repository
- awscli installed
- `/opt/mc/bootstrap.sh` + `/opt/mc/shutdown.sh` (from this folder)
- No `.env` file — cloud-init writes the runtime bits into `/opt/mc/s3.env` on each boot

Approximate time: 15–20 minutes.

## Prerequisites

- Hetzner Cloud account with billing enabled
- SSH key uploaded to Hetzner (Console → Security → SSH Keys → Add SSH Key) — note the numeric ID
- Object Storage bucket created (Console → Object Storage → Create Bucket, region sgp1) — note the endpoint, bucket name, access key, secret key
- API token created (Console → Security → API Tokens → Create with Read & Write scope) — save it somewhere

## Step 1 — Provision a base VPS

Hetzner Console → **Servers → New Server**:

- Location: **Singapore (sgp1)**
- Image: **Ubuntu 24.04**
- Type: **CPX21** (small; this VPS is temporary)
- SSH key: pick yours
- Name: `mc-base`

Wait ~30s for it to boot. Note the public IPv4.

## Step 2 — Install everything on the base VPS

SSH in from your controller / laptop:

```bash
ssh root@<vps-ip>

# Docker Engine
apt update
apt install -y ca-certificates curl git awscli
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Clone the repo to /opt/mc
git clone https://github.com/komiwalnut/Minecraft-Server.git /opt/mc
cd /opt/mc

# Copy the two VPS scripts to /opt/mc/ so they're at fixed paths.
cp deploy/bootstrap.sh deploy/shutdown.sh /opt/mc/
chmod +x /opt/mc/bootstrap.sh /opt/mc/shutdown.sh

# Sanity: pull the MC image now so the snapshot has it pre-cached.
docker pull itzg/minecraft-server:latest

# Ensure world dir exists (empty is fine).
mkdir -p /opt/mc/minecraft/data

# DO NOT create /opt/mc/.env — cloud-init writes /opt/mc/s3.env on each boot.
```

## Step 3 — Sanity-check bootstrap will work

We can't test the full bootstrap flow (needs S3 creds passed via cloud-init), but confirm the scripts don't have syntax errors:

```bash
bash -n /opt/mc/bootstrap.sh && echo "bootstrap.sh OK"
bash -n /opt/mc/shutdown.sh && echo "shutdown.sh OK"
docker --version
docker compose version
aws --version
```

## Step 4 — Clean up before snapshot

```bash
# Empty apt caches for a smaller snapshot
apt clean

# Trim SSH host keys so every VPS gets fresh ones on first boot
rm -f /etc/ssh/ssh_host_*
truncate -s0 /var/log/*.log 2>/dev/null || true
truncate -s0 /var/log/**/*.log 2>/dev/null || true

# Sync + power off
sync
poweroff
```

Wait until Hetzner Console shows the server as **"off"**.

## Step 5 — Snapshot the VPS

Console → click the server → **Snapshots** tab → **Create Snapshot**.

- Description: `mc-base v1`

Wait for the snapshot to reach status **available** (~1–3 minutes for a small system).

**Record the numeric snapshot ID** shown in the URL or the snapshot list — this goes into `HETZNER_SNAPSHOT_ID` in the controller's `.env`.

## Step 6 — Destroy the base VPS

Console → server → **⋯ menu → Delete**.

The snapshot lives on independently — Hetzner charges €0.0119/GB/month for snapshots, so a ~5 GB snapshot is ~€0.06/month. Cheap.

## Step 7 — First run

Fill in these `.env` fields on the controller box:

```
MODE=hetzner
HETZNER_API_TOKEN=<your token>
HETZNER_SNAPSHOT_ID=<from step 5>
HETZNER_LOCATION=sgp1
HETZNER_SSH_KEY_ID=<numeric ID of the SSH key you added to Hetzner>
HETZNER_SSH_PRIVATE_KEY_PATH=/root/.ssh/id_ed25519   # path on the controller
HETZNER_S3_ENDPOINT=https://sgp1.your-objectstorage.com
HETZNER_S3_BUCKET=<bucket name>
HETZNER_S3_ACCESS_KEY=<key>
HETZNER_S3_SECRET_KEY=<secret>
HETZNER_S3_WORLD_PREFIX=worlds/latest/
RCON_PASSWORD=<pick a strong one>
```

Restart the control-API. `/start-server` from Discord should now:

1. Call Hetzner API to create a VPS from the snapshot (~30s to `running`).
2. Cloud-init writes `/opt/mc/s3.env`, runs `bootstrap.sh`.
3. `bootstrap.sh` pulls world from S3 (empty on first ever run — MC generates fresh), starts the container.
4. Controller polls RCON every 60s (via the control-API's `/status`).
5. Bot's `/start-server` command edits its Discord message when state → `running`.

## Updating the snapshot later

If you need to update the base image (new Docker version, new bootstrap script, etc.):

1. Boot a new VPS from the current snapshot.
2. Make your changes.
3. Follow Steps 4–5 to snapshot again.
4. Update `HETZNER_SNAPSHOT_ID` in `.env` and restart the control-API.
5. Delete the old snapshot in the console to stop paying for it.

## Troubleshooting

**`/start-server` succeeds but MC never comes up.** SSH into the MC VPS while it's still alive and check `/var/log/mc-bootstrap.log`. Most likely: bad S3 creds, wrong bucket region, or cloud-init hasn't finished (`cloud-init status`).

**`shutdown.sh` fails with "file-count mismatch".** MC still holds file locks. The script sleeps 3s after `save-off` but Java can be slow — bump the sleep to 10s in `shutdown.sh` if you hit this.

**RCON times out from the controller.** Hetzner firewall may be blocking 25575 from the controller's IP. Add an inbound rule allowing TCP 25575 from the controller box's public IP.

**Old MC VPS stuck.** If the controller dies mid-flight, an orphan MC VPS may remain. The control-API tries to adopt it on restart (looks for `label:mc-ondemand=1`) — check the Hetzner console and delete manually if needed.
