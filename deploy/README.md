# deploy/ — VPS-side scripts and snapshot recipe

Files in this folder run **on the MC VPS**, not on the controller.

- `bootstrap.sh` — runs on VPS first boot via cloud-init. Pulls the latest world from Object Storage, starts the MC container.
- `shutdown.sh` — runs on the MC VPS via SSH from the controller when `/stop-server` fires. Flushes world, stops container, syncs to Object Storage, verifies.
- `BUILD-SNAPSHOT.md` — one-time recipe to build the base VPS and turn it into a Hetzner snapshot.

Model B setup workflow: follow `BUILD-SNAPSHOT.md` once, then the control-API's `HetznerBackend` uses the resulting snapshot for every `/start-server` invocation.
