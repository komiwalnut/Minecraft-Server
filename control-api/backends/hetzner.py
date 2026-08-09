"""Hetzner Cloud backend — stub.

Flipping MODE=local -> MODE=hetzner will import THIS file instead of
local_docker.py. Nothing else changes.

Fill in the bodies below when you're ready to migrate. The upstream API and
S3 SDK docs you'll need:
  - Hetzner Cloud API:   https://docs.hetzner.cloud/
  - hcloud-python SDK:   https://github.com/hetznercloud/hcloud-python
  - Hetzner Object Storage (S3-compatible): use boto3 with endpoint_url

Rough shape of what each method should do:
  start(tier):
    1. POST /servers to Hetzner with image=<HETZNER_SNAPSHOT_ID>,
       server_type=<tier>, location=HETZNER_LOCATION.
    2. Wait for "running" status.
    3. Pull the world down from Object Storage into the VPS via cloud-init
       or a small post-boot script, then start the MC container on it.
  stop(backup):
    1. RCON save-all flush + save-off (same as local_docker).
    2. Upload world folder to Object Storage (boto3 sync-style).
    3. Verify object count / total bytes match source before proceeding.
    4. DELETE /servers/<id>.
  status():
    1. GET /servers/<id> — map Hetzner state to ServerState.
    2. If running, RCON `list` for player count.
"""

from __future__ import annotations

import os

from .base import Backend, ServerState, ServerStatus


class HetznerBackend(Backend):
    def __init__(self) -> None:
        self.token = os.environ.get("HETZNER_API_TOKEN", "")
        self.snapshot_id = os.environ.get("HETZNER_SNAPSHOT_ID", "")
        self.location = os.environ.get("HETZNER_LOCATION", "sin1")
        self.server_name = os.environ.get("HETZNER_SERVER_NAME", "mc-ondemand")
        self.ssh_key_id = os.environ.get("HETZNER_SSH_KEY_ID", "")
        self.s3_endpoint = os.environ.get("HETZNER_S3_ENDPOINT", "")
        self.s3_bucket = os.environ.get("HETZNER_S3_BUCKET", "")
        self.s3_access = os.environ.get("HETZNER_S3_ACCESS_KEY", "")
        self.s3_secret = os.environ.get("HETZNER_S3_SECRET_KEY", "")

        missing = [k for k, v in {
            "HETZNER_API_TOKEN": self.token,
            "HETZNER_SNAPSHOT_ID": self.snapshot_id,
            "HETZNER_S3_BUCKET": self.s3_bucket,
        }.items() if not v]
        if missing:
            raise RuntimeError(
                "MODE=hetzner but these .env fields are empty: "
                + ", ".join(missing)
                + ". See .env.example for the full list."
            )

    def start(self, tier: str) -> None:
        raise NotImplementedError("Hetzner backend not yet implemented.")

    def stop(self, backup: bool = True) -> None:
        raise NotImplementedError("Hetzner backend not yet implemented.")

    def status(self) -> ServerStatus:
        return ServerStatus(state=ServerState.STOPPED, message="Hetzner backend stub.")

    def player_count(self) -> int:
        return -1
