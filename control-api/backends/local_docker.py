"""Local Docker backend — runs the itzg/minecraft-server container via `docker compose`.

Uses `docker compose --profile <tier>` (matching Phase 1's compose file) so the
same resource caps apply. World backup on stop is a filesystem copy, verified
by file count before the container is destroyed.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from mcrcon import MCRcon

from .base import Backend, ServerState, ServerStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "minecraft" / "data"
BACKUP_ROOT = REPO_ROOT / "minecraft" / "backup"


class LocalDockerBackend(Backend):
    def __init__(self) -> None:
        self._tier: Optional[str] = None
        self._started_at: Optional[float] = None
        self._transient_state: Optional[ServerState] = None
        # Cache the RCON password once; it must match docker-compose's RCON_PASSWORD.
        self._rcon_password = os.environ.get("RCON_PASSWORD", "changeme_local_only")

    # ---- helpers ----

    def _container(self, tier: Optional[str] = None) -> str:
        return f"mc-{tier or self._tier or 'cpx21'}"

    def _running_container(self) -> Optional[str]:
        # Find whichever mc-* container is running, so status() works even after
        # a control-API restart (we lose self._tier but not the container).
        for tier in ("cpx21", "cpx31"):
            name = f"mc-{tier}"
            r = subprocess.run(
                ["docker", "ps", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=10,
            )
            if r.stdout.strip() == name:
                if self._tier is None:
                    self._tier = tier  # recover from restart
                return name
        return None

    def _rcon_players(self) -> tuple[int, list[str]]:
        try:
            with MCRcon("127.0.0.1", self._rcon_password, port=25575, timeout=3) as rcon:
                r = rcon.command("list")
        except Exception:
            return -1, []
        # "There are 2 of a max of 10 players online: alice, bob"
        m = re.match(r"There are\s+(\d+)\s+of a max of\s+\d+\s+players online:?\s*(.*)$", r)
        if not m:
            return -1, []
        count = int(m.group(1))
        names_str = m.group(2).strip()
        names = [n.strip() for n in names_str.split(",")] if names_str else []
        return count, names

    # ---- Backend API ----

    def start(self, tier: str) -> None:
        if tier not in ("cpx21", "cpx31"):
            raise ValueError(f"tier must be cpx21 or cpx31, got {tier!r}")
        if self._running_container() is not None:
            raise RuntimeError("A Minecraft container is already running.")

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._tier = tier
        self._transient_state = ServerState.STARTING
        self._started_at = time.monotonic()

        subprocess.run(
            ["docker", "compose", "--profile", tier, "up", "-d"],
            cwd=REPO_ROOT, check=True, timeout=120,
        )
        # We don't wait here — status() will report STARTING until RCON answers.

    def stop(self, backup: bool = True) -> None:
        container = self._running_container()
        if container is None:
            self._transient_state = ServerState.STOPPED
            return

        self._transient_state = ServerState.STOPPING
        tier = self._tier or "cpx21"

        # 1. Flush world to disk.
        try:
            subprocess.run(
                ["docker", "exec", container, "rcon-cli", "save-all", "flush"],
                check=False, timeout=30, capture_output=True,
            )
            subprocess.run(
                ["docker", "exec", container, "rcon-cli", "save-off"],
                check=False, timeout=30, capture_output=True,
            )
        except subprocess.TimeoutExpired:
            # We still try to back up — better a stale save than no save.
            pass

        # 2. Back up the world BEFORE teardown. Must succeed or we bail.
        if backup:
            if not DATA_DIR.exists():
                raise RuntimeError(f"World directory not found at {DATA_DIR} — refusing to stop.")
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            target = BACKUP_ROOT / f"{tier}-{stamp}"
            target.mkdir(parents=True, exist_ok=True)

            # Copy tree; ignore lock files that Java may still hold.
            shutil.copytree(DATA_DIR, target, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("*.lock", "session.lock"))

            src_count = sum(1 for _ in DATA_DIR.rglob("*") if _.is_file())
            dst_count = sum(1 for _ in target.rglob("*") if _.is_file())
            # Allow a small delta for lock files we skipped.
            if abs(src_count - dst_count) > 2:
                raise RuntimeError(
                    f"Backup verification failed: {src_count} source vs {dst_count} in backup. "
                    f"NOT stopping container. Backup lives at {target}."
                )

        # 3. Tear down.
        subprocess.run(
            ["docker", "compose", "--profile", tier, "down"],
            cwd=REPO_ROOT, check=True, timeout=60,
        )
        self._transient_state = ServerState.STOPPED
        self._started_at = None

    def status(self) -> ServerStatus:
        container = self._running_container()
        if container is None:
            return ServerStatus(state=ServerState.STOPPED)

        if self._transient_state == ServerState.STOPPING:
            return ServerStatus(state=ServerState.STOPPING, tier=self._tier,
                                message="Backing up world and shutting down.")

        # If RCON answers, we're running. Otherwise still starting.
        count, names = self._rcon_players()
        uptime = int(time.monotonic() - self._started_at) if self._started_at else None
        if count < 0:
            return ServerStatus(state=ServerState.STARTING, tier=self._tier,
                                uptime_s=uptime,
                                message="Container up, waiting on RCON (world gen / jar load).")
        return ServerStatus(
            state=ServerState.RUNNING,
            tier=self._tier,
            uptime_s=uptime,
            player_count=count,
            players=names,
        )

    def player_count(self) -> int:
        # Fast path for the idle watcher; skips container-list check to keep this cheap.
        count, _ = self._rcon_players()
        return count
