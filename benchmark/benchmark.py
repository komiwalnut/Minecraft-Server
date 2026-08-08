"""Poll the running Minecraft container for TPS + resource usage and log to CSV.

Records one sample every --interval seconds:
  timestamp, tier, sample_s, players, tps, mspt, cpu_pct, mem_used_mb, mem_pct

TPS/MSPT are read via RCON. Vanilla 1.21+ exposes `/tick query rate`; older
versions and Paper/Fabric variants use different commands, so we probe a few
and remember what worked. CPU / memory come from `docker stats --no-stream`.

Usage:
  python benchmark.py --tier cpx21 --duration 600 --label "5 players building"
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from mcrcon import MCRcon
except ImportError:
    print("Missing dependency: pip install -r benchmark/requirements.txt", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "benchmark" / "reports"


@dataclass
class Sample:
    ts: str
    tier: str
    sample_s: float
    players: int
    tps: Optional[float]
    mspt: Optional[float]
    cpu_pct: Optional[float]
    mem_used_mb: Optional[float]
    mem_pct: Optional[float]


# ---------- RCON probes ----------
# Different server flavors expose TPS differently. Each probe returns
# (tps, mspt) or (None, None) if it doesn't apply to this server.
#
# Order matters: we try modern vanilla first, then fall through.

_TICK_QUERY_RE = re.compile(r"([\d.]+)\s*ms.*?([\d.]+)\s*tps", re.IGNORECASE)
_FORGE_TPS_RE  = re.compile(r"Mean tick time:\s*([\d.]+)\s*ms.*?Mean TPS:\s*([\d.]+)", re.IGNORECASE)
_PAPER_TPS_RE  = re.compile(r"TPS from last.*?([\d.]+),\s*([\d.]+),\s*([\d.]+)", re.IGNORECASE)


def _probe_vanilla_tick(rcon: MCRcon) -> tuple[Optional[float], Optional[float]]:
    # 1.21+: "Target tick rate: 20.0 per second.\nAverage time per tick: 4.32ms (target 50.00ms)"
    try:
        r = rcon.command("tick query rate")
    except Exception:
        return None, None
    if "Unknown or incomplete command" in r or "Incorrect argument" in r:
        return None, None
    # Extract mspt and derive tps from it, clamped at 20.
    m = re.search(r"Average time per tick:\s*([\d.]+)\s*ms", r)
    if not m:
        return None, None
    mspt = float(m.group(1))
    tps = min(20.0, 1000.0 / mspt) if mspt > 0 else 20.0
    return tps, mspt


def _probe_forge_tps(rcon: MCRcon) -> tuple[Optional[float], Optional[float]]:
    try:
        r = rcon.command("forge tps")
    except Exception:
        return None, None
    m = _FORGE_TPS_RE.search(r)
    if not m:
        return None, None
    return float(m.group(2)), float(m.group(1))


def _probe_paper_tps(rcon: MCRcon) -> tuple[Optional[float], Optional[float]]:
    try:
        r = rcon.command("tps")
    except Exception:
        return None, None
    m = _PAPER_TPS_RE.search(r)
    if not m:
        return None, None
    # Paper reports 1m/5m/15m — take the 1m value; no mspt available here.
    return float(m.group(1)), None


TPS_PROBES = [_probe_vanilla_tick, _probe_forge_tps, _probe_paper_tps]


def read_tps(rcon: MCRcon, cached_probe_idx: list[int]) -> tuple[Optional[float], Optional[float]]:
    # cached_probe_idx is a 1-element list used as a mutable ref so we remember
    # which probe worked and skip the others on subsequent calls.
    if cached_probe_idx[0] is not None:
        return TPS_PROBES[cached_probe_idx[0]](rcon)
    for i, probe in enumerate(TPS_PROBES):
        tps, mspt = probe(rcon)
        if tps is not None:
            cached_probe_idx[0] = i
            return tps, mspt
    return None, None


def read_player_count(rcon: MCRcon) -> int:
    try:
        r = rcon.command("list")
    except Exception:
        return -1
    # "There are 3 of a max of 10 players online: alice, bob, carol"
    m = re.search(r"There are\s+(\d+)", r)
    return int(m.group(1)) if m else -1


# ---------- docker stats ----------

def read_docker_stats(container: str) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (cpu_pct, mem_used_mb, mem_pct) via `docker stats --no-stream`."""
    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format",
             "{{json .}}", container],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None, None, None
    if not out:
        return None, None, None

    try:
        d = json.loads(out)
    except json.JSONDecodeError:
        return None, None, None

    def _pct(s: str) -> Optional[float]:
        try:
            return float(s.strip().rstrip("%"))
        except (ValueError, AttributeError):
            return None

    cpu_pct = _pct(d.get("CPUPerc", ""))
    mem_pct = _pct(d.get("MemPerc", ""))

    # MemUsage looks like "512MiB / 4GiB" — parse the left side.
    mem_used_mb: Optional[float] = None
    mu = d.get("MemUsage", "")
    m = re.match(r"([\d.]+)\s*(KiB|MiB|GiB|B)", mu)
    if m:
        val = float(m.group(1))
        unit = m.group(2)
        mem_used_mb = {
            "B":   val / (1024 * 1024),
            "KiB": val / 1024,
            "MiB": val,
            "GiB": val * 1024,
        }[unit]
    return cpu_pct, mem_used_mb, mem_pct


# ---------- main loop ----------

def run(tier: str, duration: int, interval: int, label: str, rcon_password: str) -> Path:
    container = f"mc-{tier}"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label)[:40] if label else "run"
    out_path = REPORTS_DIR / f"{tier}_{safe_label}_{stamp}.csv"

    fields = ["ts", "tier", "sample_s", "players", "tps", "mspt",
              "cpu_pct", "mem_used_mb", "mem_pct"]

    probe_idx: list[int] = [None]  # mutable ref for read_tps cache
    started = time.monotonic()
    samples_written = 0

    print(f"Benchmarking {container} for {duration}s @ {interval}s intervals")
    print(f"Label : {label}")
    print(f"Output: {out_path}")

    with MCRcon("127.0.0.1", rcon_password, port=25575) as rcon, \
         out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()

        while True:
            elapsed = time.monotonic() - started
            if elapsed >= duration:
                break

            tps, mspt = read_tps(rcon, probe_idx)
            players = read_player_count(rcon)
            cpu, mem_mb, mem_pct = read_docker_stats(container)

            s = Sample(
                ts=dt.datetime.now().isoformat(timespec="seconds"),
                tier=tier,
                sample_s=round(elapsed, 1),
                players=players,
                tps=tps,
                mspt=mspt,
                cpu_pct=cpu,
                mem_used_mb=round(mem_mb, 1) if mem_mb is not None else None,
                mem_pct=mem_pct,
            )
            w.writerow(s.__dict__)
            fh.flush()
            samples_written += 1

            print(f"  t={s.sample_s:>5}s  players={players}  "
                  f"tps={tps if tps is not None else '?'}  "
                  f"mspt={mspt if mspt is not None else '?'}  "
                  f"cpu={cpu}%  mem={mem_mb}MB ({mem_pct}%)")

            time.sleep(interval)

    print(f"\nWrote {samples_written} samples to {out_path}")
    return out_path


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tier", required=True, choices=["cpx21", "cpx31"],
                    help="Which tier profile is currently running")
    ap.add_argument("--duration", type=int, default=600,
                    help="How long to benchmark, in seconds (default: 600)")
    ap.add_argument("--interval", type=int, default=10,
                    help="Seconds between samples (default: 10)")
    ap.add_argument("--label", default="run",
                    help="Short label describing the load scenario (e.g., '5-bots-mining')")
    ap.add_argument("--rcon-password", default="changeme_local_only",
                    help="RCON password; must match RCON_PASSWORD used in docker-compose")
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args.tier, args.duration, args.interval, args.label, args.rcon_password)
