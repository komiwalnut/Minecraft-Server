# Deploy to Hetzner Cloud

Two deployment models. Pick based on how much your server will actually be used.

- **Model A — Always-on VPS.** One CPX21/CPX31 runs everything 24/7. **No new code required.** Cheapest to build, ~€8–15/month regardless of usage.
- **Model B — On-demand VPS.** A tiny controller box provisions the MC VPS from a snapshot when players want it, destroys it when idle. World in Object Storage. Cheapest per-play-hour, most complex. **Requires implementing the currently-stubbed `HetznerBackend`.**

Both require your bot to already be deployed somewhere (Render, per [bot/README.md](../bot/README.md#deploying-to-render-later)). If you don't have a bot deployed yet, run local (see [LOCAL-DEV.md](LOCAL-DEV.md)) — the cloud is not required for testing.

---

## Model A — Always-on VPS (recommended first)

The control-API and MC container run on the same Hetzner VPS. `MODE=local` on the VPS — the `local_docker` backend manages the MC container on the same host, exactly like on your laptop.

### Costs (approx, 2026-08)

| Item | Monthly |
|---|---|
| Hetzner CPX21 (3 vCPU / 4 GB) | ~€8 |
| Hetzner CPX31 (4 vCPU / 8 GB) | ~€15 |
| Backups (optional, +20%) | +€1.60 / +€3.00 |

Latest prices: https://www.hetzner.com/cloud.

### Step 1 — Provision the VPS

Hetzner Console → **Servers → New Server**.

- Location: **Singapore (sgp1)**
- Image: **Ubuntu 24.04**
- Type: **CPX21** or **CPX31** (from your benchmarks — see [BENCHMARKING.md](BENCHMARKING.md))
- SSH key: add yours
- Name: `mc-server`

Wait for it to boot. Note the public IPv4.

### Step 2 — Install Docker

SSH in and install Docker Engine (not Docker Desktop):

```bash
ssh root@<vps-ip>

apt update
apt install -y ca-certificates curl git python3-venv python3-pip
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

docker --version
docker compose version
```

### Step 3 — Clone the repo and configure

```bash
git clone https://github.com/komiwalnut/Minecraft-Server.git /opt/mc
cd /opt/mc

cp .env.example .env
# Edit — set STRONG values for these:
#   RCON_PASSWORD=<random>
#   CONTROL_API_TOKEN=<random>
# Everything else keeps its default.
nano .env
```

### Step 4 — Install control-API dependencies

```bash
cd /opt/mc/control-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
```

### Step 5 — Open ports in the Hetzner firewall

Console → **Firewalls → Create Firewall**. Inbound rules:

| Protocol | Port | Source | Purpose |
|---|---|---|---|
| TCP | 22 | Your home IP only | SSH |
| TCP | 25565 | Anywhere | Minecraft |
| TCP | 8080 | Anywhere | Control-API (auth is by bearer token) |

Attach the firewall to your server.

> **Note on port 8080:** we're opening it to the world but auth is enforced by the bearer token. If you want stricter, whitelist your Render outbound IPs (Render publishes them at https://render.com/docs/network-addresses). Even better: put HTTPS + a reverse proxy in front of it — see the *HTTPS* section below.

### Step 6 — Run the control-API as a systemd service

`/etc/systemd/system/mc-control-api.service`:

```ini
[Unit]
Description=MC control-API
After=docker.service network.target
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/mc/control-api
Environment="PATH=/opt/mc/control-api/.venv/bin:/usr/bin"
EnvironmentFile=/opt/mc/.env
ExecStart=/opt/mc/control-api/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8080
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

Note `--host 0.0.0.0` — bind to all interfaces so the bot (on Render) can reach it.

```bash
systemctl daemon-reload
systemctl enable --now mc-control-api
systemctl status mc-control-api
journalctl -u mc-control-api -f    # follow logs
```

### Step 7 — Verify from your laptop

```powershell
curl http://<vps-ip>:8080/health
# {"ok":true,"mode":"local"}

curl -H "Authorization: Bearer <your CONTROL_API_TOKEN>" http://<vps-ip>:8080/status
# {"state":"stopped","tier":null,...}
```

### Step 8 — Point the Render'd bot at the VPS

Render dashboard → your bot service → **Environment**:

- `CONTROL_API_URL` = `http://<vps-ip>:8080`
- `CONTROL_API_TOKEN` = matching value from VPS `.env`

Save. Render redeploys.

### Step 9 — Test end-to-end

In Discord: `/start-server`. The bot calls Render → VPS control-API → `docker compose up` → RCON polling → the bot edits its message when the server is ready.

Connect from Minecraft to `<vps-ip>:25565`.

### HTTPS (recommended once basic setup works)

Buy a cheap domain, point an A record at your VPS. On the VPS:

```bash
apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```
mc-api.yourdomain.com {
    reverse_proxy 127.0.0.1:8080
}
```

```bash
systemctl restart caddy
```

Update Render `CONTROL_API_URL` → `https://mc-api.yourdomain.com`. Close port 8080 in the Hetzner firewall (Caddy handles 80/443, Let's Encrypt cert is automatic).

### World backups

Model A stores backups locally at `/opt/mc/minecraft/backup/`. Cheap ways to persist off-VPS:

- **Hetzner Backups.** Console → server → Backups. +20% of VPS cost. Daily automatic snapshots of the whole disk.
- **Rsync to Object Storage.** Cron job that syncs `minecraft/backup/` to a Hetzner Object Storage bucket. Cheaper per GB than full-disk backups.

### Uninstall

If you want to move to Model B later, or just tear this down:

```bash
systemctl disable --now mc-control-api
docker compose --profile cpx21 down
docker compose --profile cpx31 down
# Snapshot the VPS if you plan to redeploy (needed for Model B anyway).
# Then destroy the VPS in the Hetzner console.
```

---

## Model B — On-demand VPS (advanced)

The "you only pay when someone plays" architecture. A tiny always-on controller runs the control-API and the Discord bot. When someone hits `/start-server`, the controller calls Hetzner's API to provision an MC VPS from a snapshot, boots it with the latest world pulled from Object Storage, and hands the connection info back to the user. `/stop-server` uploads the world back to Object Storage and destroys the MC VPS.

### When it's worth the extra work

- Server runs less than ~10–14 hours/day on average.
- You're willing to write ~200 lines of Python against the Hetzner API and boto3.

Below that usage, Model A is simpler and comparably priced.

### Architecture

```
Discord ──▶ Bot (Render, ~free)
              │
              ▼
       Controller box (Hetzner CX22, ~€4/month, always on)
              │  runs control-API in MODE=hetzner
              │
              ├─ Hetzner Cloud API ──▶ MC VPS (CPX21/31, only alive while playing)
              │                          runs docker-compose up on boot via cloud-init
              │
              └─ Hetzner Object Storage ──▶ world backups
```

### Prerequisites (do these once)

**1. Do Model A first.** You need a working Model A deployment to snapshot from.

**2. Create a snapshot.** Once Model A works: `docker compose --profile cpx21 down` on the VPS, then Console → server → **Snapshots → Create Snapshot**. Note the numeric snapshot ID → goes into `HETZNER_SNAPSHOT_ID` in the controller's `.env`.

**3. Create an Object Storage bucket.** Console → **Object Storage → Create Bucket**. Region: sgp1. Note endpoint, bucket name, access key, secret key → goes into the `HETZNER_S3_*` fields.

**4. Create a Hetzner API token.** Console → **Security → API Tokens** → Create with **Read & Write** scope → into `HETZNER_API_TOKEN`.

**5. Provision the controller box.** A separate small VPS (CX22, ~€4/month) is enough. Install the code the same way as Model A, but only run the control-API on it — no MC container. Also install the Discord bot here if you don't want to use Render.

**6. Bake a bootstrap script into the snapshot.** The snapshot needs a `/opt/mc/bootstrap.sh` that runs on boot to pull the world and start MC:

```bash
#!/bin/bash
# /opt/mc/bootstrap.sh — runs on VPS boot via cloud-init.
set -euo pipefail

# Read S3 creds passed in via cloud-init user-data.
source /opt/mc/s3.env

# Sync latest world down from Object Storage.
apt install -y awscli
aws --endpoint-url "$HETZNER_S3_ENDPOINT" s3 sync \
    "s3://$HETZNER_S3_BUCKET/$HETZNER_S3_WORLD_PREFIX" \
    /opt/mc/minecraft/data/

# Start the MC container.
cd /opt/mc
docker compose --profile "${TIER:-cpx21}" up -d
```

Re-snapshot the VPS after adding this file. Set `HETZNER_SNAPSHOT_ID` to the new snapshot.

### What you need to implement

`control-api/backends/hetzner.py` currently raises `NotImplementedError` for all three methods. Fill them in:

**`start(tier)`** — provision a VPS and wait for it to be ready.

```python
# Pseudo-code sketch
def start(self, tier):
    # 1. Call Hetzner API to create the server.
    resp = httpx.post(
        "https://api.hetzner.cloud/v1/servers",
        headers={"Authorization": f"Bearer {self.token}"},
        json={
            "name": self.server_name,
            "server_type": tier,
            "image": int(self.snapshot_id),
            "location": self.location,
            "ssh_keys": [int(self.ssh_key_id)],
            "user_data": self._bootstrap_userdata(tier),  # cloud-init to write s3.env then run bootstrap.sh
        },
    )
    self._server_id = resp.json()["server"]["id"]
    self._public_ip = resp.json()["server"]["public_net"]["ipv4"]["ip"]
    # 2. Return quickly — status() will report starting until RCON answers.
```

**`stop(backup)`** — sync world to Object Storage, verify, then destroy the VPS.

```python
def stop(self, backup=True):
    # 1. SSH in (or hit a small VPS-local endpoint) to run: docker exec mc-* rcon-cli save-all flush.
    # 2. If backup: aws s3 sync minecraft/data/ s3://.../worlds/latest/ — verify object count.
    # 3. If backup verification passed:
    httpx.delete(
        f"https://api.hetzner.cloud/v1/servers/{self._server_id}",
        headers={"Authorization": f"Bearer {self.token}"},
    )
    self._server_id = None
```

**`status()`** — VPS state + RCON player count.

```python
def status(self):
    if not self._server_id:
        return ServerStatus(state=ServerState.STOPPED)
    resp = httpx.get(
        f"https://api.hetzner.cloud/v1/servers/{self._server_id}",
        headers={"Authorization": f"Bearer {self.token}"},
    ).json()
    hz_state = resp["server"]["status"]  # "running", "starting", "off", ...
    if hz_state != "running":
        return ServerStatus(state=ServerState.STARTING, tier=..., message=hz_state)
    # If running, query RCON on the VPS's public IP.
    with MCRcon(self._public_ip, self._rcon_password, port=25575, timeout=3) as r:
        r = r.command("list")
    # parse and return ServerStatus(state=RUNNING, player_count=..., players=...)
```

### Switching over

```bash
# On the controller box:
# 1. Fill in all HETZNER_* fields in .env.
# 2. Change MODE=local -> MODE=hetzner.
# 3. Restart the control-API.
systemctl restart mc-control-api
```

The bot doesn't know or care. Same URLs, same auth.

### Cost outline (Model B)

| Item | Monthly |
|---|---|
| Hetzner CX22 (controller, always on) | ~€4 |
| Hetzner CPX21 MC VPS (assume 4h/day active) | ~€1.30 (€8 × 4/24) |
| Hetzner Object Storage (10 GB world data) | ~€1 |
| **Total** | **~€6–7** |

Compare Model A CPX21: ~€8. Model B wins when actual server-up hours drop below ~55% of the month.

### Gotchas

- **First boot from snapshot is slow.** Cloud-init needs to run, world needs to download from S3, MC needs to start. Expect 3–5 min. The bot's poll timeout is 5 min — you may want to bump it.
- **World corruption is unrecoverable across VPS lifecycles.** Model B relies on the upload-then-destroy sequence being atomic. My `stop()` sketch above uploads before destroying — do NOT skip the verify step.
- **RCON over the internet.** The controller needs to reach `<mc-vps-ip>:25575`. Either open port 25575 with a strong RCON password, or set up a private Hetzner network between controller and MC VPS.

---

## Which do I do?

- **First cloud deploy, want it working today**: Model A.
- **Model A working for weeks, usage is bursty, want to save money**: switch to B.
- **Never done cloud infra before**: Model A, and use Hetzner Backups for peace of mind.
