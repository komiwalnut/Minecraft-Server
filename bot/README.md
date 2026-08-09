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

Pattern matches Jobbilee (`../reference/Jobbilee/bot.js`) so if you already know that bot, you already know this one.

## First-time Discord setup

1. Create a **new** application at https://discord.com/developers/applications (don't reuse Jobbilee's).
2. Under **Bot** → reset the token → copy it into `bot/.env` as `DISCORD_TOKEN`.
3. Under **OAuth2 → URL Generator**, scopes `bot` + `applications.commands`. Permissions: `Send Messages`, `Embed Links`. Invite the bot to your server with the generated URL.
4. Get your admin role ID (Discord → Settings → Advanced → Developer Mode ON → right-click role → Copy Role ID) and put it in `bot/.env` as `MC_ADMIN_ROLE_ID`. Default in code matches yours: `1535796235376795728`.

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

**The bot MUST run locally during Phase 3 dev** because the control-API listens on `localhost:8080` and a bot hosted on Render can't reach that.

## Deploying to Render (later)

Once the Hetzner VPS is up and the control-API is reachable at a public URL:

1. Push this `bot/` directory to a GitHub repo (or use monorepo root + `bot/` root-directory setting).
2. Render → New → Web Service → connect the repo.
3. Environment variables — set all of:
   - `DISCORD_TOKEN`
   - `CONTROL_API_URL` = `https://<vps-hostname>`
   - `CONTROL_API_TOKEN` = matching value from control-API
   - `MC_ADMIN_ROLE_ID`
4. Set up UptimeRobot to ping the Render URL every 5 min (same trick Jobbilee uses).

## Commands

| Command | Access | Behavior |
|---|---|---|
| `/start-server [tier]` | Role `MC_ADMIN_ROLE_ID` only | POSTs `/start`, polls `/status` until `running` (5-min timeout) |
| `/stop-server` | Role `MC_ADMIN_ROLE_ID` only | POSTs `/stop` with `backup: true`. Errors if backup fails; server stays up. |
| `/server-status` | Everyone in guild | GETs `/status`, renders an embed |

## Role gating notes

Discord ships `interaction.member.roles.cache` inline with every slash-command interaction payload. The bot uses only the `Guilds` intent — no privileged `GuildMembers` intent needed, no user in the guild has to be pre-fetched.

If the role check fails, the bot replies ephemerally ("You need the required role…") — only the invoking user sees it.
