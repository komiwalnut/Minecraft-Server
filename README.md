# Minecraft-Server — on-demand Discord-triggered Minecraft

Local-first development for a Discord-triggered Minecraft server that will eventually run on Hetzner Cloud (Singapore, CPX21 or CPX31). Vanilla, target <10 concurrent players.

## Status

- **Phase 1 — Local Docker with tier simulation:** done. Two Compose profiles cap CPU + memory to mimic Hetzner CPX21 (3 vCPU / 4 GB) and CPX31 (4 vCPU / 8 GB).
- **Phase 2 — Benchmark harness:** done. RCON-based TPS logger, Mineflayer load simulator, comparison report generator.
- **Phase 3 — Discord bot integration:** planned in `docs/PHASE3-PLAN.md`, not yet implemented.

## Prerequisites

- Docker Desktop (Windows) running.
- Python 3.10+ (for the benchmark harness).
- Node.js 18+ (for the Mineflayer load simulator).
- ~5 GB free disk (server jar + world + Docker image).

## Layout

```
docker-compose.yml            # both tier profiles
scripts/                      # .ps1 + .sh mirrors for start/stop
minecraft/                    # (gitignored) world data + backups
  data/                       # world lives here — swap for S3 later
  backup/                     # timestamped copies on stop --backup
benchmark/
  benchmark.py                # RCON + docker-stats poller → CSV
  report.py                   # CSVs → comparison markdown + tier recommendation
  load_sim/                   # Mineflayer bots
  reports/                    # (gitignored) CSVs land here
docs/
  PHASE2-TESTPLAN.md          # how to run the benchmark matrix
  PHASE3-PLAN.md              # bot/control-API design + Render caveats
reference/                    # (gitignored) read-only clone of the Discord bot
.env.example                  # config template with MODE=local/hetzner
```

## Phase 1 — Run the server locally

```powershell
# Start CPX21 simulation (3 vCPU / 4 GB / 3 GB heap)
.\scripts\start.ps1 -Tier cpx21

# Or CPX31 simulation (4 vCPU / 8 GB / 6 GB heap)
.\scripts\start.ps1 -Tier cpx31 -Follow    # -Follow tails the logs

# Stop, with world backup copied to minecraft/backup/<timestamp>/
.\scripts\stop.ps1 -Tier cpx21 -Backup
```

Linux mirrors (`scripts/start.sh`, `scripts/stop.sh`) exist for later deploy to the Hetzner VPS.

Connect from a Minecraft client to `localhost:25565`. RCON is exposed on `25575` for the benchmark harness.

### JVM heap notes

The container memory caps are the *whole container*, not just the JVM. So heap is set **below** the cap:

| Tier   | Container RAM | INIT_MEMORY | MAX_MEMORY | Headroom for JVM overhead + page cache |
|--------|---------------|-------------|------------|---------------------------------------|
| CPX21  | 4 GB          | 2 GB        | 3 GB       | ~1 GB                                 |
| CPX31  | 8 GB          | 4 GB        | 6 GB       | ~2 GB                                 |

Setting `-Xmx` equal to the container limit will get the JVM OOM-killed under load, so don't.

## Phase 2 — Benchmark

1. Install Python + Node dependencies (one time):

   ```powershell
   pip install -r benchmark\requirements.txt
   cd benchmark\load_sim ; npm install ; cd ..\..
   ```

2. Enable offline mode so Mineflayer bots can connect (see `benchmark/load_sim/README.md` — creates `docker-compose.override.yml` locally, gitignored).

3. Run the matrix documented in `docs/PHASE2-TESTPLAN.md`. Rough shape per scenario:

   ```powershell
   # Terminal A — server
   .\scripts\start.ps1 -Tier cpx21

   # Terminal B — logger
   python benchmark\benchmark.py --tier cpx21 --duration 600 --label medium-5bots

   # Terminal C — load
   cd benchmark\load_sim
   node bots.js --count 5 --duration 600
   ```

4. Once you have runs across both tiers and load levels:

   ```powershell
   python benchmark\report.py
   # writes benchmark/reports/comparison.md with a tier recommendation
   ```

## Phase 3 — Discord bot (planned, not yet built)

See **`docs/PHASE3-PLAN.md`** for the design. Short version:

- The Jobbilee bot repo (referenced) already has a slash-command loader — new commands are dropped-in files matching `commands/price.js`'s shape.
- A separate small **control API** (FastAPI) sits between the bot and Docker/Hetzner. Bot never touches infra directly.
- Migration from local Docker to Hetzner is a **one-line config change**: flip `MODE=local` → `MODE=hetzner` in the control API's `.env` (all Hetzner fields are already placeholdered in `.env.example`).
- **Render caveat, flagged:** a bot running on Render **cannot reach a Docker container on your laptop**. During Phase 3 dev you'll either run the bot locally or use a tunnel — details in `docs/PHASE3-PLAN.md`.

Three open questions before Phase 3 code lands — see the bottom of `docs/PHASE3-PLAN.md`.

## Configuration switch (Phase 3 preview)

Copy `.env.example` → `.env` and edit. The blocks marked HETZNER MODE are placeholders; you fill them in when the VPS exists. Nothing in `docker-compose.yml` or `scripts/` needs to change to migrate — those are the local layer, replaced entirely (not modified) by the Hetzner backend in the control API.

## License

MIT (see `LICENSE`).
