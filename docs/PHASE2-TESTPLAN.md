# Phase 2 — Load test plan

The benchmark harness measures TPS + CPU + memory during a run. You still need to **generate** the load. Two ways:

1. **Automated (bots).** Fast, repeatable, doesn't need friends. Slightly less realistic than humans.
2. **Manual (real players).** More realistic, especially for redstone/building patterns bots don't produce.

Run each tier through each load level. Recommended durations: **10 min per run** — long enough for chunk-load spikes to settle and mob-cap effects to appear, short enough that you'll actually finish.

## Matrix

Each cell is one benchmark run. `bots` = Mineflayer, `players` = real people.

| Load level | Scenario | How to reproduce |
|---|---|---|
| Idle | Server up, no one connected | Just run the server for 10 min |
| Light (2) | 2 bots OR 2 players | Bots: `--count 2 --duration 600` |
| Medium (5) | 5 bots OR 5 players building | Bots: `--count 5 --duration 600` |
| Heavy (10) | 10 bots OR 10 players | Bots: `--count 10 --duration 600` |

Do the matrix once per tier (cpx21 and cpx31). Optionally re-run "Heavy" with real players for validation.

## Per-run recipe

Terminal A — start the server (do this once per tier):

```powershell
.\scripts\start.ps1 -Tier cpx21
# Wait until logs show "Done ()! For help, type "help""
```

Terminal B — start the benchmark harness (do this once per scenario):

```powershell
python benchmark\benchmark.py --tier cpx21 --duration 600 --label "medium-5bots"
```

Terminal C — kick off the load (bots OR ask your friends to join):

```powershell
cd benchmark\load_sim
node bots.js --count 5 --duration 600
```

Wait for both B and C to finish, then move to the next scenario.

## Manual player scenarios

If you're using real players instead of bots, ask them to do a mix of:
- **Explore** in different directions (chunk generation load — highest CPU spike).
- **Build** something with 50+ blocks (network + block-update load).
- **Farm mobs** or afk at a mob farm if you have one (entity tick load).
- **Redstone contraption** running (block-update tick storms if modded — smaller vanilla impact).

## When you're done

```powershell
python benchmark\report.py
# reads all CSVs in benchmark/reports/, writes comparison.md with a tier recommendation
```

## Interpreting the numbers

- **TPS.** 20 is perfect. 19-20 is fine. 15-19 = players feel occasional lag. <15 = obvious lag; mob AI freezes.
- **MSPT.** Time to compute one tick. Should be <50ms. Anything approaching 50ms means TPS is about to drop.
- **CPU%.** Docker reports per-cgroup — 300% means saturating 3 of your 3 allotted cores. Sustained >90% of your cap = you'll drop TPS under any additional load.
- **Memory.** Should sit comfortably below your `MAX_MEMORY` (3GB on CPX21, 6GB on CPX31). If it's pinned at the ceiling, GC pressure will crater TPS.
