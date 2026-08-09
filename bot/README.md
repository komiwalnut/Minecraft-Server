# bot — Minecraft-Server Discord bot

Node.js + discord.js v14. Slash commands only. All infra work (starting/stopping the server, backing up the world) is done by the **control-API** — the bot is just a thin HTTP client with role gating.

## Layout

```
bot.js            # entrypoint: loads commands/, registers slash commands, HTTP keep-alive
lib/api.js        # shared control-API client + role check + helpers
commands/
  start-server.js
  stop-server.js
  server-status.js
```

## First-time Discord setup

1. Create an application at https://discord.com/developers/applications.
2. Under **Bot** → reset the token → copy it into `bot/.env` as `DISCORD_TOKEN`.
3. Under **OAuth2 → URL Generator**, scopes `bot` + `applications.commands`. Permissions: `View Channel`, `Send Messages`, `Embed Links` (integer `19456`). Leave all Privileged Gateway Intents OFF. Invite the bot to your server with the generated URL.
4. Get your admin role ID (Discord → Settings → Advanced → Developer Mode ON → right-click role → Copy Role ID) and put it in `bot/.env` as `MC_ADMIN_ROLE_ID`. Default in code: `1535796235376795728`.

## Local dev

```powershell
cd bot
copy .env.example .env    # then edit DISCORD_TOKEN
npm install
npm start
```

Expected output:

```
Keep-alive server listening on port 3000
Logged in as YourBot#1234
Registered 3 slash command(s): /start-server, /stop-server, /server-status
```

**During local dev the bot must run locally too** — a bot on Render can't reach `localhost:8080` on your machine. If you also have a Render deploy, suspend the Render service while testing locally. See [../docs/LOCAL-DEV.md](../docs/LOCAL-DEV.md).

## Deploying to Render

Render supports monorepo deploys via the **Root Directory** setting.

1. Render → **New +** → **Web Service** → connect this repo.
2. Service settings:
   - **Root Directory:** `bot`
   - **Runtime:** Node
   - **Build Command:** `npm install`
   - **Start Command:** `npm start`
   - **Region:** Singapore (matches your Hetzner target)
3. Environment variables:
   - `DISCORD_TOKEN` — from Discord Developer Portal
   - `CONTROL_API_URL` — the URL of your deployed control-API (see [../docs/DEPLOY-HETZNER.md](../docs/DEPLOY-HETZNER.md))
   - `CONTROL_API_TOKEN` — matching value from the control-API's `.env`
   - `MC_ADMIN_ROLE_ID`
4. Prevent free-tier spin-down: create an UptimeRobot HTTP monitor for the Render URL, 5-min interval.

## Commands

| Command | Access | Behavior |
|---|---|---|
| `/start-server [tier]` | Role `MC_ADMIN_ROLE_ID` only | POSTs `/start`, polls `/status` until `running` (5-min timeout) |
| `/stop-server` | Role `MC_ADMIN_ROLE_ID` only | POSTs `/stop` with `backup: true`. Errors if backup fails; server stays up. |
| `/server-status` | Everyone in guild | GETs `/status`, renders an embed |

## Role gating notes

Discord ships `interaction.member.roles.cache` inline with every slash-command interaction payload. The bot uses only the `Guilds` intent — no privileged `GuildMembers` intent needed, no user in the guild has to be pre-fetched.

If the role check fails, the bot replies ephemerally ("You need the required role…") — only the invoking user sees it.
