# Local development

Run the whole stack (MC server + control-API + Discord bot) on your own machine. This is the primary development mode and also the fastest way to try the project.

## Prerequisites

- **Docker Desktop** (Windows or macOS) — hosts the MC container.
- **Python 3.10+** — control-API.
- **Node.js 18+** — Discord bot (also needed for the Mineflayer load simulator).
- **A Discord bot application** — see [bot/README.md](../bot/README.md#first-time-discord-setup) for creating one.
- **A Minecraft account** if you want to actually connect and play (server runs in online-mode by default).

## One-time setup

```powershell
git clone https://github.com/komiwalnut/Minecraft-Server.git
cd Minecraft-Server

# Root .env (RCON password, control-API token, idle threshold)
copy .env.example .env
# Defaults work for local dev — no edits required.

# Bot .env (Discord token, admin role ID)
cd bot
copy .env.example .env
notepad .env    # set DISCORD_TOKEN and MC_ADMIN_ROLE_ID
npm install
cd ..

# Control-API dependencies
cd control-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
deactivate
cd ..
```

## Running the stack (3 terminals)

**Terminal 1 — MC container:**

```powershell
.\scripts\start.ps1 -Tier cpx21
# Use -Tier cpx31 for the 8 GB profile
```

First run downloads ~150 MB (Docker image) and generates the world (~30–60 s). Follow with `docker logs -f mc-cpx21` if you want to watch.

**Terminal 2 — Control-API:**

```powershell
cd control-api
.\.venv\Scripts\Activate.ps1
.\run.ps1
```

Sanity check from any other terminal:

```powershell
curl http://127.0.0.1:8080/health
# {"ok":true,"mode":"local"}
```

**Terminal 3 — Discord bot:**

```powershell
cd bot
npm start
```

Expected output:

```
Keep-alive server listening on port 3000
Logged in as YourBot#1234
Registered 3 slash command(s): /server-status, /start-server, /stop-server
```

## Test end-to-end

In your Discord server:

1. `/server-status` — anyone can run. Should show `running`, `cpx21`, 0 players.
2. Open your Minecraft launcher, add server `localhost`, connect. Rerun `/server-status` — player count = 1, your username listed.
3. `/stop-server` (needs admin role) — bot reports "Backing up world and stopping". Look for `minecraft\backup\cpx21-<timestamp>\`.
4. `/start-server` (needs admin role) — bot polls every 10 s and edits its reply when the server hits `running`.

## Idle shutdown

The control-API polls RCON every 60 s. If the server has **0 players for `IDLE_SHUTDOWN_MINUTES` consecutive minutes** (default 15), it runs the same shutdown flow as `/stop-server`. Adjust in root `.env`.

## Bot deployed to Render? Suspend it during local testing

You can't have two instances of the same Discord bot running simultaneously — Discord routes each interaction to only one. If your bot is also deployed on Render:

- Render dashboard → your service → **Suspend Web Service** before local testing.
- Resume when done.

Alternative: expose your local control-API via a tunnel (Cloudflare Tunnel or ngrok) and point Render's `CONTROL_API_URL` at that URL, so the Render bot keeps running.

## Troubleshooting

**MC container exits with `UnsupportedClassVersionError` / class file version 69 error.** The MC version needs a newer JVM than the pinned image tag. `docker-compose.yml` uses `itzg/minecraft-server:latest`, which auto-tracks the right runtime — if you changed it, revert.

**`/server-status` hangs indefinitely.** MC 1.21+ auto-pauses the server thread after 60 s empty, which breaks RCON. `docker-compose.yml` sets `PAUSE_WHEN_EMPTY_SECONDS: "0"` to disable this — the control-API's idle watcher handles shutdown instead. If you removed the setting, the API will hang until someone joins.

**Bot says "Could not reach the control API".** Verify the control-API is running (`curl http://127.0.0.1:8080/health`). If the bot is on Render, remember Render can't reach your laptop — either suspend it or use a tunnel.

**Slash commands don't autocomplete in Discord.** Global slash commands take up to an hour to propagate. Type the command manually the first time.

**`/start-server` says "You need the required role".** Check `MC_ADMIN_ROLE_ID` in `bot/.env` against your role. Get IDs: Discord Settings → Advanced → Developer Mode ON → right-click a role → Copy Role ID.

**Backup verification fails on `/stop-server`.** The stop path copies `minecraft/data/` to `minecraft/backup/<tier>-<timestamp>/` and compares file counts. If they differ by more than 2 (accounting for lock files), the container is NOT torn down. Investigate the backup folder before retrying.
