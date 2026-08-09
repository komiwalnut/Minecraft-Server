"""Backend contract — every implementation must satisfy this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ServerState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ServerStatus:
    state: ServerState
    tier: Optional[str] = None
    uptime_s: Optional[int] = None
    player_count: int = 0
    players: list[str] = field(default_factory=list)
    # Free-form field for the UI to surface — "booting jar", "backing up world", etc.
    message: Optional[str] = None


class Backend(ABC):
    """One backend = one way to run the MC server (local Docker, Hetzner VPS, ...)."""

    @abstractmethod
    def start(self, tier: str) -> None:
        """Kick off server boot. Return quickly; callers poll status() for READY."""

    @abstractmethod
    def stop(self, backup: bool = True) -> None:
        """Save world, back it up, then tear down. Must raise if backup fails."""

    @abstractmethod
    def status(self) -> ServerStatus:
        """Return current status. Cheap — will be called ~every 60s by the idle watcher."""

    @abstractmethod
    def player_count(self) -> int:
        """Live player count via RCON. Returns -1 if the server isn't answering RCON."""
