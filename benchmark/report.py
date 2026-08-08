"""Aggregate benchmark CSVs into a comparison markdown report.

Reads all CSVs in benchmark/reports/ and produces a table of avg/min TPS,
avg/peak CPU, avg/peak memory, grouped by tier and label. Emits a tier
recommendation based on TPS floor:

  - If both tiers hold TPS >= 19.0 at 10 players → recommend CPX21 (cheaper).
  - Else if CPX31 holds and CPX21 doesn't → recommend CPX31.
  - Else neither is sufficient → recommend Paper server or CPX41+.

Usage:
  python report.py                        # writes reports/comparison.md
  python report.py --format json          # writes reports/comparison.json
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "benchmark" / "reports"


def _floatish(x: str) -> float | None:
    if x in ("", "None", None):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def aggregate() -> dict:
    """Return {(tier, label): {stats...}} over all CSVs."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for csv_path in sorted(REPORTS_DIR.glob("*.csv")):
        # Filename format: <tier>_<label>_<stamp>.csv
        stem = csv_path.stem
        parts = stem.split("_")
        if len(parts) < 3:
            continue
        tier = parts[0]
        label = "_".join(parts[1:-1]) or "run"
        with csv_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                groups[(tier, label)].append(row)

    def _stats(values: list[float | None]) -> dict:
        clean = [v for v in values if v is not None]
        if not clean:
            return {"n": 0}
        return {
            "n": len(clean),
            "avg": round(statistics.mean(clean), 2),
            "min": round(min(clean), 2),
            "max": round(max(clean), 2),
            "p05": round(statistics.quantiles(clean, n=20)[0], 2) if len(clean) >= 20 else None,
        }

    out: dict = {}
    for (tier, label), rows in groups.items():
        max_players = max(int(r.get("players") or 0) for r in rows)
        out.setdefault(tier, {})[label] = {
            "samples": len(rows),
            "max_players_seen": max_players,
            "tps": _stats([_floatish(r.get("tps", "")) for r in rows]),
            "mspt": _stats([_floatish(r.get("mspt", "")) for r in rows]),
            "cpu_pct": _stats([_floatish(r.get("cpu_pct", "")) for r in rows]),
            "mem_used_mb": _stats([_floatish(r.get("mem_used_mb", "")) for r in rows]),
        }
    return out


def recommend(data: dict) -> str:
    # Look for high-load scenarios (max_players >= 8) and compare TPS floors.
    def _worst_tps(tier: str) -> float | None:
        vals = []
        for label, s in data.get(tier, {}).items():
            if s["max_players_seen"] >= 8 and s["tps"]["n"] > 0:
                vals.append(s["tps"]["min"])
        return min(vals) if vals else None

    c21 = _worst_tps("cpx21")
    c31 = _worst_tps("cpx31")

    lines = []
    lines.append(f"CPX21 worst-case TPS at ≥8 players: {c21 if c21 is not None else 'no data'}")
    lines.append(f"CPX31 worst-case TPS at ≥8 players: {c31 if c31 is not None else 'no data'}")

    if c21 is None and c31 is None:
        lines.append("")
        lines.append("**Recommendation:** Run at least one 10-player benchmark on each tier before deciding.")
    elif c21 is not None and c21 >= 19.0:
        lines.append("")
        lines.append("**Recommendation: CPX21.** It holds ≥19 TPS at your target load. CPX31 is unnecessary spend.")
    elif c31 is not None and c31 >= 19.0:
        lines.append("")
        lines.append("**Recommendation: CPX31.** CPX21 drops below 19 TPS, CPX31 handles it.")
    else:
        lines.append("")
        lines.append("**Recommendation:** Neither tier holds acceptable TPS. Options:")
        lines.append("  1. Switch server to Paper/Purpur (huge TPS gains from Lithium-style optimizations).")
        lines.append("  2. Reduce view/simulation distance in `docker-compose.yml`.")
        lines.append("  3. Upgrade to CPX41 or CCX-series (dedicated vCPU) — those extra cores actually help.")
    return "\n".join(lines)


def to_markdown(data: dict) -> str:
    md = ["# Benchmark comparison\n"]
    for tier in sorted(data.keys()):
        md.append(f"## Tier: {tier}\n")
        md.append("| Scenario | Samples | Max players | Avg TPS | Min TPS | Avg MSPT | Avg CPU% | Peak CPU% | Avg mem (MB) | Peak mem (MB) |")
        md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for label, s in sorted(data[tier].items()):
            tps, mspt, cpu, mem = s["tps"], s["mspt"], s["cpu_pct"], s["mem_used_mb"]
            md.append(
                f"| {label} | {s['samples']} | {s['max_players_seen']} | "
                f"{tps.get('avg','-')} | {tps.get('min','-')} | "
                f"{mspt.get('avg','-')} | "
                f"{cpu.get('avg','-')} | {cpu.get('max','-')} | "
                f"{mem.get('avg','-')} | {mem.get('max','-')} |"
            )
        md.append("")
    md.append("## Recommendation\n")
    md.append(recommend(data))
    md.append("")
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--format", choices=["md", "json"], default="md")
    args = ap.parse_args()

    data = aggregate()
    if not data:
        print(f"No CSVs found in {REPORTS_DIR}. Run benchmark.py first.")
        return

    if args.format == "json":
        out = REPORTS_DIR / "comparison.json"
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    else:
        out = REPORTS_DIR / "comparison.md"
        out.write_text(to_markdown(data), encoding="utf-8")

    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
