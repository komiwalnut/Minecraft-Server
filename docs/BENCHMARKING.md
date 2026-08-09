# Benchmarking

Skip this doc if you already know which Hetzner tier you want. Otherwise, run the harness locally to simulate CPX21 (3 vCPU / 4 GB) and CPX31 (4 vCPU / 8 GB) under realistic load, and pick based on data.

## Matrix

Once per tier — each cell is one 10-minute run:

| Load | Scenario | How |
|---|---|---|
| Idle | Server up, no one connected | Just let it run |
| Light | 2 players/bots | `--count 2 --duration 600` |
| Medium | 5 players/bots | `--count 5 --duration 600` |
| Heavy | 10 players/bots | `--count 10 --duration 600` |

## Per-run recipe

Three terminals:

**T1 — server:**
```powershell
.\scripts\start.ps1 -Tier cpx21
# Wait for "Done" in logs, then Ctrl+C the tail.
```

**T2 — logger (one invocation per scenario):**
```powershell
python benchmark\benchmark.py --tier cpx21 --duration 600 --label medium-5bots
```

Writes `benchmark/reports/cpx21_medium-5bots_<timestamp>.csv`.

**T3 — load:**

Automated (Mineflayer bots):
```powershell
cd benchmark\load_sim
npm install    # first time only
node bots.js --count 5 --duration 600
```

Or manual: ask real players to join and mix exploring, building, farming.

## Enable offline mode for Mineflayer bots

Mineflayer can't authenticate against Mojang for free, so bots need offline-mode. Create `docker-compose.override.yml` (gitignored) at repo root:

```yaml
services:
  mc-cpx21:
    environment:
      ONLINE_MODE: "false"
  mc-cpx31:
    environment:
      ONLINE_MODE: "false"
```

Remove this override before exposing the server publicly — offline mode lets anyone connect as any username.

## Report

Once you have runs across both tiers and load levels:

```powershell
python benchmark\report.py
```

Writes `benchmark/reports/comparison.md` with a table per tier and a recommendation based on worst-case TPS at ≥8 players.

## Reading the numbers

- **TPS**: 20 = perfect. 19–20 = fine. 15–19 = occasional lag noticed by players. <15 = obvious lag, mob AI freezes.
- **MSPT**: milliseconds per tick. Should stay <50. Approaching 50 means TPS is about to drop.
- **CPU%**: Docker reports per-cgroup. 300% = using all 3 of your CPX21 cores. Sustained >90% of your cap = you'll lose TPS under any additional load.
- **Memory**: should sit comfortably below `MAX_MEMORY` (3 GB CPX21, 6 GB CPX31). If it's pinned at the ceiling, GC pressure will crater TPS regardless of CPU headroom.

## Recommendations the report emits

- Both tiers hold ≥19 TPS at 10 players → **CPX21** (save the money).
- CPX21 drops below 19, CPX31 holds → **CPX31**.
- Neither holds → switch server type (Paper/Purpur handles small VPS much better than vanilla), reduce view/simulation distance, or upgrade to CPX41/CCX-series (dedicated vCPU).
