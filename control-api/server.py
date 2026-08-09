"""Control-API — HTTP layer between the Discord bot and the actual server backend.

Runs at localhost:8080 in local dev; move to the Hetzner VPS in prod and
change nothing else (the bot only knows CONTROL_API_URL from .env).

Endpoints:
  GET  /health           -> {"ok": true, "mode": "local"}
  GET  /status           -> ServerStatus
  POST /start            -> 202 {"accepted": true}; body: {"tier": "cpx21"}
  POST /stop             -> 202 {"accepted": true}; body: {"backup": true}

All routes except /health require:
  Authorization: Bearer <CONTROL_API_TOKEN>
"""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

# Load repo-root .env early so the backend factory sees MODE=... and friends.
REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

from backends import get_backend  # noqa: E402 — must be after load_dotenv
from backends.base import ServerState  # noqa: E402

log = logging.getLogger("control-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# ---------- config ----------

MODE = os.environ.get("MODE", "local").lower()
CONTROL_API_TOKEN = os.environ.get("CONTROL_API_TOKEN", "changeme_local_only")
IDLE_SHUTDOWN_MINUTES = int(os.environ.get("IDLE_SHUTDOWN_MINUTES", "15"))

# Set at startup after we successfully build the backend.
BACKEND = None


# ---------- idle watcher ----------

class IdleWatcher:
    """Polls player count. If zero for IDLE_SHUTDOWN_MINUTES straight, calls stop().

    Runs in a daemon thread so it dies with the process. Backend calls are
    synchronous, which is fine — this thread is the only one doing them from
    outside a request context.
    """

    def __init__(self, backend, idle_minutes: int, poll_interval_s: int = 60):
        self.backend = backend
        self.idle_seconds = idle_minutes * 60
        self.poll_interval_s = poll_interval_s
        self._last_nonzero_at: Optional[float] = None
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="idle-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()

    def _run(self) -> None:
        log.info("Idle watcher started (threshold: %d min)", self.idle_seconds // 60)
        while not self._stop_evt.wait(self.poll_interval_s):
            try:
                s = self.backend.status()
            except Exception as e:
                log.warning("idle-watcher status() failed: %s", e)
                continue

            if s.state != ServerState.RUNNING:
                self._last_nonzero_at = None
                continue

            if s.player_count > 0:
                self._last_nonzero_at = time.monotonic()
                continue

            # 0 players. Prime the timer on the first zero-poll after players leave.
            if self._last_nonzero_at is None:
                self._last_nonzero_at = time.monotonic()
                continue

            idle_for = time.monotonic() - self._last_nonzero_at
            if idle_for >= self.idle_seconds:
                log.info("Server idle for %.0fs (>= %ds threshold) — triggering shutdown",
                         idle_for, self.idle_seconds)
                try:
                    self.backend.stop(backup=True)
                    log.info("Idle shutdown complete.")
                except Exception as e:
                    log.exception("Idle shutdown failed: %s", e)
                self._last_nonzero_at = None


IDLE = None


# ---------- app lifespan ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global BACKEND, IDLE
    BACKEND = get_backend()
    log.info("Backend: %s (MODE=%s)", type(BACKEND).__name__, MODE)
    IDLE = IdleWatcher(BACKEND, IDLE_SHUTDOWN_MINUTES)
    IDLE.start()
    yield
    if IDLE:
        IDLE.stop()


app = FastAPI(title="Minecraft control API", lifespan=lifespan)


# ---------- auth ----------

def require_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {CONTROL_API_TOKEN}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or missing bearer token.")


# ---------- schemas ----------

class StartBody(BaseModel):
    tier: str = Field(default="cpx21", pattern="^(cpx21|cpx31)$")


class StopBody(BaseModel):
    backup: bool = True


# ---------- routes ----------

@app.get("/health")
def health() -> dict:
    return {"ok": True, "mode": MODE}


@app.get("/status", dependencies=[Depends(require_token)])
def get_status() -> dict:
    s = BACKEND.status()
    return {
        "state": s.state.value,
        "tier": s.tier,
        "uptime_s": s.uptime_s,
        "player_count": s.player_count,
        "players": s.players,
        "message": s.message,
    }


@app.post("/start", status_code=202, dependencies=[Depends(require_token)])
def post_start(body: StartBody) -> dict:
    try:
        BACKEND.start(body.tier)
    except RuntimeError as e:
        # Already running or missing config — surface cleanly to the bot.
        raise HTTPException(status_code=409, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    return {"accepted": True, "tier": body.tier}


@app.post("/stop", status_code=202, dependencies=[Depends(require_token)])
def post_stop(body: StopBody) -> dict:
    try:
        BACKEND.stop(backup=body.backup)
    except RuntimeError as e:
        # Backup verification failure — do NOT report success.
        raise HTTPException(status_code=500, detail=str(e))
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    return {"accepted": True}
