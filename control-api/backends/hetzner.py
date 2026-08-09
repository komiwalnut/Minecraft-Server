"""Hetzner Cloud backend — provisions an MC VPS on demand.

Lifecycle:
  start(tier):
    1. POST /servers with image=<snapshot>, server_type=<tier>, cloud-init
       user-data that writes /opt/mc/s3.env and runs /opt/mc/bootstrap.sh.
    2. Record the server id + public IP so status()/stop() can find it.
    3. Return immediately. status() will report STARTING until RCON answers.

  stop(backup):
    1. SSH into the VPS, run /opt/mc/shutdown.sh.
       That script does: RCON save-all flush + save-off → docker compose
       down → aws s3 sync world → object-count check.
       Exit code 0 means backup is on disk in S3.
    2. Independently verify from the controller: list the S3 prefix and
       confirm at least one object exists that was modified in the last
       10 minutes.
    3. Only if BOTH checks pass, call DELETE /servers/<id>.

  status():
    - No server id → STOPPED.
    - Hetzner state != "running" → STARTING (with the raw state as message).
    - Hetzner running + RCON answers → RUNNING (with live player count).
    - Hetzner running + RCON silent → STARTING (world gen / MC boot).

State (server id, public IP, tier) lives in-memory. If the controller box
is restarted mid-flight, we try to recover by listing Hetzner servers with
the label we set at creation (label: `mc-ondemand=1`).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import boto3
import httpx
import paramiko
from mcrcon import MCRcon

from .base import Backend, ServerState, ServerStatus

log = logging.getLogger("control-api.hetzner")

HETZNER_API = "https://api.hetzner.cloud/v1"
CREATION_LABEL_KEY = "mc-ondemand"
CREATION_LABEL_VAL = "1"

# Cloud-init user-data. The bootstrap script is already baked into the
# snapshot at /opt/mc/bootstrap.sh; we only write the env file it needs.
USERDATA_TEMPLATE = """#cloud-config
write_files:
  - path: /opt/mc/s3.env
    permissions: '0600'
    owner: root:root
    content: |
      TIER={tier}
      RCON_PASSWORD={rcon_password}
      HETZNER_S3_ENDPOINT={s3_endpoint}
      HETZNER_S3_BUCKET={s3_bucket}
      HETZNER_S3_ACCESS_KEY={s3_access}
      HETZNER_S3_SECRET_KEY={s3_secret}
      HETZNER_S3_WORLD_PREFIX={s3_prefix}
runcmd:
  - bash /opt/mc/bootstrap.sh
"""


class HetznerBackend(Backend):
    def __init__(self) -> None:
        self.token = os.environ["HETZNER_API_TOKEN"]
        self.snapshot_id = int(os.environ["HETZNER_SNAPSHOT_ID"])
        self.location = os.environ.get("HETZNER_LOCATION", "sgp1")
        self.server_name = os.environ.get("HETZNER_SERVER_NAME", "mc-ondemand")
        self.ssh_key_id = int(os.environ["HETZNER_SSH_KEY_ID"])
        self.ssh_key_path = Path(os.environ["HETZNER_SSH_PRIVATE_KEY_PATH"]).expanduser()
        self.rcon_password = os.environ.get("RCON_PASSWORD", "changeme_local_only")

        self.s3_endpoint = os.environ["HETZNER_S3_ENDPOINT"]
        self.s3_bucket = os.environ["HETZNER_S3_BUCKET"]
        self.s3_access = os.environ["HETZNER_S3_ACCESS_KEY"]
        self.s3_secret = os.environ["HETZNER_S3_SECRET_KEY"]
        self.s3_prefix = os.environ.get("HETZNER_S3_WORLD_PREFIX", "worlds/latest/")

        self._server_id: Optional[int] = None
        self._public_ip: Optional[str] = None
        self._tier: Optional[str] = None
        self._started_at: Optional[float] = None

        self._http = httpx.Client(
            base_url=HETZNER_API,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=15.0,
        )
        self._s3 = boto3.client(
            "s3",
            endpoint_url=self.s3_endpoint,
            aws_access_key_id=self.s3_access,
            aws_secret_access_key=self.s3_secret,
            region_name=self.location,
        )

        # Recover state if the controller restarted while a VPS was live.
        self._try_recover_state()

    # ---------- Hetzner API helpers ----------

    def _try_recover_state(self) -> None:
        """Find a running MC VPS from a previous controller lifetime, if any."""
        try:
            r = self._http.get(
                "/servers",
                params={"label_selector": f"{CREATION_LABEL_KEY}={CREATION_LABEL_VAL}"},
            )
            r.raise_for_status()
            servers = r.json().get("servers", [])
        except Exception as e:
            log.warning("Could not query Hetzner for existing MC VPS: %s", e)
            return
        if not servers:
            return
        # Adopt the first (there should never be more than one).
        s = servers[0]
        self._server_id = s["id"]
        self._public_ip = s["public_net"]["ipv4"]["ip"]
        self._tier = s["server_type"]["name"]
        log.info("Recovered running MC VPS: id=%s ip=%s tier=%s",
                 self._server_id, self._public_ip, self._tier)

    def _create_server(self, tier: str) -> dict:
        userdata = USERDATA_TEMPLATE.format(
            tier=tier,
            rcon_password=self.rcon_password,
            s3_endpoint=self.s3_endpoint,
            s3_bucket=self.s3_bucket,
            s3_access=self.s3_access,
            s3_secret=self.s3_secret,
            s3_prefix=self.s3_prefix,
        )
        r = self._http.post("/servers", json={
            "name": self.server_name,
            "server_type": tier,
            "image": self.snapshot_id,
            "location": self.location,
            "ssh_keys": [self.ssh_key_id],
            "user_data": userdata,
            "labels": {CREATION_LABEL_KEY: CREATION_LABEL_VAL, "tier": tier},
            "start_after_create": True,
        })
        r.raise_for_status()
        return r.json()["server"]

    def _get_server(self, server_id: int) -> Optional[dict]:
        r = self._http.get(f"/servers/{server_id}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()["server"]

    def _delete_server(self, server_id: int) -> None:
        r = self._http.delete(f"/servers/{server_id}")
        # 200 with an action envelope, or 404 if already gone. Both are fine.
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()

    # ---------- SSH + verification ----------

    def _run_shutdown_script(self) -> str:
        """SSH into the VPS, run /opt/mc/shutdown.sh, return combined stdout+stderr.

        Raises RuntimeError if the script exits non-zero or if we can't connect.
        """
        if not self._public_ip:
            raise RuntimeError("No public IP on record for the VPS.")

        key = paramiko.Ed25519Key.from_private_key_file(str(self.ssh_key_path)) \
            if self.ssh_key_path.exists() and self._is_ed25519(self.ssh_key_path) \
            else paramiko.RSAKey.from_private_key_file(str(self.ssh_key_path))

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                self._public_ip, port=22, username="root", pkey=key,
                timeout=15, banner_timeout=15, auth_timeout=15,
            )
            stdin, stdout, stderr = client.exec_command(
                "bash /opt/mc/shutdown.sh 2>&1", timeout=600,
            )
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            exit_code = stdout.channel.recv_exit_status()
            combined = out + err
            if exit_code != 0:
                raise RuntimeError(
                    f"shutdown.sh exited {exit_code}. Last output:\n{combined[-2000:]}"
                )
            return combined
        finally:
            client.close()

    @staticmethod
    def _is_ed25519(path: Path) -> bool:
        try:
            head = path.read_text(errors="replace").splitlines()[0]
        except Exception:
            return False
        return "OPENSSH" in head  # Ed25519 uses OpenSSH format

    def _verify_backup_in_s3(self, min_age_seconds: int = 600) -> int:
        """Return the number of world objects whose LastModified is within
        the last `min_age_seconds`. Raise if none.
        """
        recent_cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=min_age_seconds)
        recent = 0
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.s3_bucket, Prefix=self.s3_prefix):
            for obj in page.get("Contents", []):
                if obj["LastModified"] >= recent_cutoff:
                    recent += 1
        if recent == 0:
            raise RuntimeError(
                f"S3 verification failed: no objects modified in the last "
                f"{min_age_seconds}s under s3://{self.s3_bucket}/{self.s3_prefix}. "
                f"NOT destroying VPS."
            )
        return recent

    # ---------- RCON ----------

    def _rcon_players(self) -> tuple[int, list[str]]:
        if not self._public_ip:
            return -1, []
        try:
            with MCRcon(self._public_ip, self.rcon_password, port=25575, timeout=3) as rcon:
                r = rcon.command("list")
        except Exception:
            return -1, []
        m = re.match(r"There are\s+(\d+)\s+of a max of\s+\d+\s+players online:?\s*(.*)$", r)
        if not m:
            return -1, []
        count = int(m.group(1))
        names_str = m.group(2).strip()
        names = [n.strip() for n in names_str.split(",")] if names_str else []
        return count, names

    # ---------- Backend contract ----------

    def start(self, tier: str) -> None:
        if tier not in ("cpx21", "cpx31"):
            raise ValueError(f"tier must be cpx21 or cpx31, got {tier!r}")
        if self._server_id is not None:
            raise RuntimeError("A Minecraft VPS is already running.")

        log.info("Creating Hetzner VPS (tier=%s, snapshot=%s, location=%s)",
                 tier, self.snapshot_id, self.location)
        server = self._create_server(tier)
        self._server_id = server["id"]
        self._public_ip = server["public_net"]["ipv4"]["ip"]
        self._tier = tier
        self._started_at = time.monotonic()
        log.info("VPS created: id=%s ip=%s. Cloud-init + bootstrap.sh now running on the VPS.",
                 self._server_id, self._public_ip)

    def stop(self, backup: bool = True) -> None:
        if self._server_id is None:
            log.info("stop() called with no VPS on record — nothing to do.")
            return

        server_id = self._server_id
        log.info("Stopping MC VPS id=%s (backup=%s)", server_id, backup)

        if backup:
            log.info("Running shutdown.sh over SSH...")
            output = self._run_shutdown_script()
            log.info("shutdown.sh output (tail):\n%s", output[-1500:])

            log.info("Verifying world backup landed in S3...")
            recent = self._verify_backup_in_s3()
            log.info("S3 verification OK: %d objects modified recently.", recent)
        else:
            log.warning("backup=False — destroying VPS WITHOUT saving world.")

        log.info("Destroying VPS id=%s", server_id)
        self._delete_server(server_id)
        self._server_id = None
        self._public_ip = None
        self._tier = None
        self._started_at = None

    def status(self) -> ServerStatus:
        if self._server_id is None:
            return ServerStatus(state=ServerState.STOPPED)

        try:
            server = self._get_server(self._server_id)
        except httpx.HTTPError as e:
            return ServerStatus(state=ServerState.ERROR, tier=self._tier,
                                message=f"Hetzner API error: {e}")
        if server is None:
            # 404 — someone destroyed it out of band.
            self._server_id = None
            self._public_ip = None
            return ServerStatus(state=ServerState.STOPPED,
                                message="VPS was destroyed out of band.")

        hz_state = server["status"]
        if hz_state != "running":
            return ServerStatus(state=ServerState.STARTING, tier=self._tier,
                                message=f"Hetzner: {hz_state}")

        # VPS is running — is MC up on it?
        count, names = self._rcon_players()
        uptime = int(time.monotonic() - self._started_at) if self._started_at else None
        if count < 0:
            return ServerStatus(state=ServerState.STARTING, tier=self._tier,
                                uptime_s=uptime,
                                message="VPS running; waiting on cloud-init + MC boot + RCON.")
        return ServerStatus(
            state=ServerState.RUNNING,
            tier=self._tier,
            uptime_s=uptime,
            player_count=count,
            players=names,
            message=f"VPS {self._public_ip}",
        )

    def player_count(self) -> int:
        count, _ = self._rcon_players()
        return count
