# control-api — HTTP layer between the bot and the server backend

FastAPI service listening on `localhost:8080`. Talks to a pluggable backend:

- `MODE=local`   → `backends/local_docker.py` (Phase 1/2 dev)
- `MODE=hetzner` → `backends/hetzner.py` (production; stubbed today)

The Discord bot never talks to Docker or Hetzner directly — it calls this API. Migration is a one-line `.env` change: flip `MODE=local` to `MODE=hetzner` and restart the API. No bot code changes.

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | none | Liveness probe. Returns `{ok, mode}`. |
| GET | `/status` | bearer | ServerStatus (state / tier / uptime / players). |
| POST | `/start` | bearer | Body: `{tier: "cpx21"\|"cpx31"}`. Returns 202 immediately; bot polls status. |
| POST | `/stop` | bearer | Body: `{backup: bool}`. World backup is verified before container teardown; endpoint returns 500 if backup fails. |

Bearer token: header `Authorization: Bearer <CONTROL_API_TOKEN>` (from root `.env`).

## Idle shutdown

A background thread polls `/status` every 60s. If `state == running` and `player_count == 0` for `IDLE_SHUTDOWN_MINUTES` consecutive minutes (default 15), it runs the same shutdown flow as `POST /stop` (world backup + verify + tear down). Configure via `IDLE_SHUTDOWN_MINUTES` in `.env`.

## Local dev

Requires the Phase 1 Docker setup to be reachable via `docker compose` from this repo root.

```powershell
cd control-api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Reads root ../.env automatically (via python-dotenv).
uvicorn server:app --host 127.0.0.1 --port 8080 --reload
```

Test:

```powershell
curl http://localhost:8080/health
curl -H "Authorization: Bearer changeme_local_only" http://localhost:8080/status
curl -H "Authorization: Bearer changeme_local_only" -H "Content-Type: application/json" `
    -d '{"tier":"cpx21"}' http://localhost:8080/start
```

## Adding a new backend

1. Add `backends/<name>.py` implementing `Backend` from `backends/base.py`.
2. Add a branch in `backends/__init__.py::get_backend()`.
3. Set `MODE=<name>` in `.env`.

No other file needs to change.

## Migration checklist: local → Hetzner

1. Provision a Hetzner Cloud VPS (CPX21 or CPX31 per your Phase 2 findings).
2. Install Docker on the VPS, `git clone` this repo there, run the server once to generate the world.
3. Snapshot the VPS in the Hetzner console — record the snapshot ID.
4. Create an Object Storage bucket for world backups.
5. Implement the three method bodies in `backends/hetzner.py` (docstring in that file has the sketch).
6. Fill `.env` with all `HETZNER_*` fields, set `MODE=hetzner`, restart uvicorn.
7. Update the bot's `CONTROL_API_URL` env var to point at the VPS.

Done. No bot code, no compose file, no script changes.
