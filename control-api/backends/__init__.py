"""Backend factory. Reads MODE from env; hands back the right implementation.

Adding a new backend later = new file in this package + one branch here.
Nothing above this layer changes."""

from __future__ import annotations

import os

from .base import Backend


def get_backend() -> Backend:
    mode = os.environ.get("MODE", "local").lower()
    if mode == "local":
        from .local_docker import LocalDockerBackend
        return LocalDockerBackend()
    if mode == "hetzner":
        from .hetzner import HetznerBackend
        return HetznerBackend()
    raise ValueError(
        f"Unknown MODE={mode!r}. Set MODE=local or MODE=hetzner in .env."
    )
