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

### When it's worth the extra complexity

Server runs less than ~10–14 hours/day on average. Below that usage, Model A is simpler and comparably priced.

The code is already written — `control-api/backends/hetzner.py` implements the backend, and `deploy/bootstrap.sh` + `deploy/shutdown.sh` handle the VPS-side lifecycle. What's left is one-time Hetzner setup (account, keys, bucket, snapshot) and configuring the controller.

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

### One-time Hetzner setup

Do these in order. Full clicks-and-values recipe: [../deploy/BUILD-SNAPSHOT.md](../deploy/BUILD-SNAPSHOT.md).

**1. SSH key.** Console → **Security → SSH Keys → Add SSH Key**. Paste your public key. Record the numeric ID → `HETZNER_SSH_KEY_ID`.

**2. API token.** Console → **Security → API Tokens → Generate API Token** with Read + Write scope → `HETZNER_API_TOKEN`.

**3. Object Storage bucket.** Console → **Object Storage → Create Bucket**, region sgp1. From the bucket detail: endpoint URL, name, access key, secret key → `HETZNER_S3_*`.

**4. Build the snapshot.** Follow [../deploy/BUILD-SNAPSHOT.md](../deploy/BUILD-SNAPSHOT.md): provision an Ubuntu 24.04 CPX21, install Docker + this repo + `bootstrap.sh`/`shutdown.sh`, snapshot it. Snapshot ID → `HETZNER_SNAPSHOT_ID`. Destroy the base VPS after snapshotting — you'll never boot into it directly again.

### Set up the controller box (Hetzner CX22)

**Provision.** Console → New Server → Location sgp1 → Ubuntu 24.04 → Type **CX22** → your SSH key → name `mc-controller`.

**Install control-API on it:**

```bash
ssh root@<controller-ip>

apt update
apt install -y python3-venv python3-pip git

git clone https://github.com/komiwalnut/Minecraft-Server.git /opt/mc
cd /opt/mc/control-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate

# Root .env — this is what the control-API reads.
cd /opt/mc
cp .env.example .env
nano .env
# Set:
#   MODE=hetzner
#   RCON_PASSWORD=<strong random>
#   CONTROL_API_TOKEN=<strong random>
#   HETZNER_API_TOKEN=<from step 2>
#   HETZNER_SNAPSHOT_ID=<from step 4>
#   HETZNER_SSH_KEY_ID=<from step 1>
#   HETZNER_SSH_PRIVATE_KEY_PATH=/root/.ssh/id_ed25519   (see below)
#   HETZNER_S3_* fields from step 3

# SSH private key: the controller uses this to SSH into MC VPS on shutdown.
# Copy or generate; make sure the corresponding public key is what you
# added in step 1.
ls -l /root/.ssh/id_ed25519
```

**Systemd unit** at `/etc/systemd/system/mc-control-api.service`:

```ini
[Unit]
Description=MC control-API
After=network.target

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

```bash
systemctl daemon-reload
systemctl enable --now mc-control-api
journalctl -u mc-control-api -f
```

**Firewall.** Console → **Firewalls → Create Firewall**. Attach to the controller:

- TCP 22 (SSH) — from your home IP
- TCP 8080 (control-API) — from Anywhere (bearer token is the auth)

For the MC VPS: no persistent firewall needed since each VPS is short-lived. Alternatively, create a second firewall with TCP 25565 open to Anywhere + TCP 25575 open from the controller IP, and label MC VPSes so the firewall auto-applies. The current code doesn't set this up — you'd add `firewalls: [<id>]` to the server-create body in `hetzner.py::_create_server`.

**Point the Render bot at the controller.** Render dashboard → your bot service → Environment:

- `CONTROL_API_URL` = `http://<controller-ip>:8080`
- `CONTROL_API_TOKEN` = matching value from controller's `.env`

Redeploy is automatic. HTTPS-via-Caddy same as Model A's HTTPS section if you want it.

### Cost outline (Model B)

| Item | Monthly |
|---|---|
| Hetzner CX22 (controller, always on) | ~€4 |
| Hetzner CPX21 MC VPS (assume 4h/day active) | ~€1.30 (€8 × 4/24) |
| Hetzner Object Storage (10 GB world data) | ~€1 |
| **Total** | **~€6–7** |

Compare Model A CPX21: ~€8. Model B wins when actual server-up hours drop below ~55% of the month.

### Gotchas

- **First boot from snapshot is slow.** Cloud-init runs, world downloads from S3, MC starts. Expect 2–4 min. The bot's `/start-server` polls for 5 min before giving up — usually fine.
- **World integrity across VPS lifecycles is critical.** The `HetznerBackend.stop()` path is upload → dual-verify (SSH script exit code + independent S3 object count) → then delete. Do not disable the verify step. If verification fails, the VPS stays up so you can SSH in and rescue the world manually.
- **RCON over the internet.** The controller reaches `<mc-vps-ip>:25575` with `RCON_PASSWORD`. Pick a strong password, and consider adding a firewall rule allowing 25575 only from the controller's public IP.
- **Orphan MC VPS.** If the controller crashes during a `/start-server`, the created VPS keeps running. On restart, the control-API tries to adopt it (looking for `label:mc-ondemand=1`). If adoption fails, delete the VPS manually in the Hetzner console.
- **Snapshots age.** The snapshot bakes in a specific Docker version + repo commit. Periodically boot from the snapshot, `git pull`, `apt upgrade`, re-snapshot. Delete the old snapshot after to stop paying for it.

---

## Which do I do?

- **First cloud deploy, want it working today**: Model A.
- **Model A working for weeks, usage is bursty, want to save money**: switch to B.
- **Never done cloud infra before**: Model A, and use Hetzner Backups for peace of mind.
