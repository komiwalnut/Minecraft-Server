# Load simulator

Mineflayer bots that wander and dig to put chunk-loading + pathfinding pressure on the server.

## Requirements

- Node 18+
- Local MC server running with `online-mode=false` (bots can't authenticate against Mojang for free — this is fine for local benchmarking, do NOT expose the server publicly like this).

## Enable offline mode

Create `docker-compose.override.yml` at the repo root:

```yaml
services:
  mc-cpx21:
    environment:
      ONLINE_MODE: "false"
  mc-cpx31:
    environment:
      ONLINE_MODE: "false"
```

This file is gitignored so your override never leaks into production.

## Run

```bash
cd benchmark/load_sim
npm install
node bots.js --count 5 --duration 300
```

Or with env vars:

```bash
BOT_COUNT=10 BOT_DURATION=600 node bots.js
```

## Notes

- Bots take ~2s each to connect (staggered to avoid the login throttle) — so 10 bots is ~20s to fully spawn.
- Each bot wanders in a random direction ~every 20s and digs blocks in its path. This produces steady chunk churn, which is the main TPS drain for small servers.
- The server's `MAX_PLAYERS` is 10 in `docker-compose.yml` — increase it if you want to test more bots.
