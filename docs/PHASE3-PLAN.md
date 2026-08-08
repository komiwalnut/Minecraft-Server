# Phase 3 plan — Discord-triggered on-demand server

> Not yet implemented. This document is the plan; code goes in when you approve the shape.

## Summary of what the Jobbilee bot already gives us

Reference clone lives at `reference/Jobbilee/` (gitignored). Key findings from reading `bot.js` and `commands/price.js`:

- **Framework:** discord.js v14 + @discordjs/voice, Node 18+.
- **Slash-command infra is already there.** `bot.js:29-34` auto-loads every `.js` in `commands/`. `bot.js:97` registers them globally on startup. `bot.js:106-140` dispatches `isChatInputCommand()` to `cmd.execute()` and `isStringSelectMenu()` to `cmd.handleSelect()` (matched via `cmd.CUSTOM_ID_PREFIX`).
- **Command shape:** each command exports `{ data: SlashCommandBuilder, execute(interaction) }`, plus optional `{ CUSTOM_ID_PREFIX, handleSelect(interaction) }`. See `commands/price.js` — it's the template.
- **Hosting:** Render web service. HTTP keep-alive server on port 3000 (`bot.js:146-151`) exists specifically so UptimeRobot can ping it to prevent Render's 15-min free-tier spin-down.
- **Currently one command:** `/price` (Steam price lookup, unrelated to Minecraft).

## The Render problem — flagged for you

**The bot on Render cannot reach your local Docker container.** No path from Render's infrastructure back to your laptop. Options during dev:

- **Option A (recommended for testing):** run the bot locally too (`node bot.js` on the same machine as Docker). Everything works. Downside: your friends can't use the commands until you go online.
- **Option B:** expose the local control API via a tunnel (Cloudflare Tunnel / ngrok). Bot on Render calls the tunnel URL. Works, but adds a moving part.
- **Option C:** skip local Docker testing of the bot and jump straight to Hetzner once Phase 2 tells you which tier. The bot on Render calls the Hetzner VPS's public IP.

**Recommendation:** A for now, then C once you're happy with the design.

## Architecture (matches your requirement that migration = one config change)

```
Discord ↔ Jobbilee bot (Node, discord.js) ↔ control-api (Python FastAPI) ↔ backend
                                                                            ├── local_docker (Phase 1/2 dev)
                                                                            └── hetzner (production)
```

The bot never talks to Docker or Hetzner directly. It calls the control API over HTTP. Swapping backends = flipping `MODE=local` to `MODE=hetzner` in the control API's `.env` and restarting it. **Zero bot code changes.**

## New files to add

```
control-api/
  server.py                    # FastAPI: /start /stop /status /health
  requirements.txt
  backends/
    __init__.py                # picks backend based on MODE env var
    base.py                    # abstract Backend class: start()/stop()/status()
    local_docker.py            # implements Backend via `docker compose`
    hetzner.py                 # implements Backend via Hetzner Cloud API + S3
  README.md

reference-jobbilee-commands/   # to be COPIED into your bot repo, NOT this one
  start-server.js
  stop-server.js
  server-status.js
  README.md                    # instructions on how to drop these into Jobbilee
```

## Command sketches

Each command is a thin HTTP client. Real logic lives in the control API.

**`/start-server`** → POST /start → 202 Accepted → bot replies "Booting… ETA ~2 min" → polls /status until ready or timeout.

**`/stop-server`** → POST /stop → control API does: kick players → save-all flush → RCON stop → verify world backup → tear down container. Bot only reports progress.

**`/server-status`** → GET /status → returns `{state, uptime_s, player_count, players[], tier}`.

## Idle timeout

Two options:

- **In the control API** (recommended): background task polls RCON `list` every 60s. Zero-player streak ≥ `IDLE_SHUTDOWN_MINUTES` triggers the same shutdown flow as `/stop-server`. Advantage: works even when the bot is offline / Render is asleep.
- In the bot: less reliable because Render's free tier may spin down the bot itself.

## The migration checklist (fill-the-blanks, no code changes)

When you're ready to switch from local Docker to Hetzner:

1. Fill in Hetzner fields in `.env` (see `.env.example` — `HETZNER_*`).
2. Change `MODE=local` → `MODE=hetzner` in `.env`.
3. Restart the control API.
4. That's it.

## Open questions before I write Phase 3 code

- [ ] Confirm: run the bot locally during dev (Option A above)?
- [ ] Confirm: control API in **Python (FastAPI)** or **Node (Express)**? Python fits Phase 2 tooling but adds a runtime; Node keeps everything in one language.
- [ ] Which Discord role/user should be allowed to run `/start-server`? Any restrictions or open to everyone in the guild?
