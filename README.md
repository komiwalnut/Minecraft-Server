# Minecraft-Server

An on-demand, Discord-triggered Minecraft server. Vanilla, up to ~10 concurrent players. Runs locally in Docker for development and on Hetzner Cloud (Singapore) in production. Server boot, shutdown, and status are triggered via Discord slash commands; auto-shuts down after a configurable idle period.

## Architecture

```
   Discord   ──slash──▶   Bot   ──HTTP+bearer──▶   Control API   ──▶   MC server (Docker)
                        Node.js                    FastAPI               itzg/minecraft-server
                                                   ├─ local_docker (dev + always-on VPS)
                                                   └─ hetzner       (on-demand VPS, stubbed)
```

- **Bot** — thin HTTP client, no infra logic. Registers `/start-server`, `/stop-server`, `/server-status`.
- **Control API** — one contract, swappable backend. Migrating from local to cloud is a `MODE=...` env flip.
- **MC server** — vanilla, in a Docker container with tier-appropriate CPU/memory caps (mimicking Hetzner CPX21 / CPX31).

## Layout

```
bot/                    # Discord bot (Node.js + discord.js v14)
control-api/            # HTTP API (FastAPI) with pluggable backend
  backends/
    local_docker.py     # runs Docker on the current host
    hetzner.py          # provisions Hetzner VPS on demand (stubbed — see DEPLOY-HETZNER.md)
docker-compose.yml      # MC container with tier profiles (cpx21 / cpx31)
scripts/                # start.ps1 / stop.ps1 with .sh mirrors for Linux
minecraft/              # world data + backups (gitignored)
benchmark/              # TPS + Mineflayer load simulator + report generator
docs/
  LOCAL-DEV.md          # full local development guide
  DEPLOY-HETZNER.md     # cloud deployment: Always-on VPS + On-demand VPS
  BENCHMARKING.md       # benchmarking harness usage
```

## Quick start

**Local:** see [docs/LOCAL-DEV.md](docs/LOCAL-DEV.md).

**Cloud deploy (Hetzner):** see [docs/DEPLOY-HETZNER.md](docs/DEPLOY-HETZNER.md).

**Not sure which tier to buy?** Run the benchmark harness: [docs/BENCHMARKING.md](docs/BENCHMARKING.md).

## Configuration

Copy `.env.example` → `.env`. The single key setting is:

- `MODE=local` — the control-API runs Docker on whatever machine it's on (your laptop for dev, or the VPS for Always-on cloud deploys).
- `MODE=hetzner` — the control-API provisions Hetzner Cloud VPS on demand. Requires the Hetzner backend to be implemented (see `docs/DEPLOY-HETZNER.md` Model B).

Every other setting has sensible defaults. `.env.example` documents every field and when you need it.

## License

MIT (see `LICENSE`).
