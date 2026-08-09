# control-api — HTTP layer between the bot and the server backend

FastAPI service listening on `localhost:8080` (or `0.0.0.0:8080` in production). Talks to a pluggable backend:

- `MODE=local`   → `backends/local_docker.py` — manages a Docker container on the same host. Used both for local dev and for the "Always-on VPS" cloud deployment.
- `MODE=hetzner` → `backends/hetzner.py` — provisions Hetzner Cloud VPS on demand. Currently stubbed; see [../docs/DEPLOY-HETZNER.md](../docs/DEPLOY-HETZNER.md) Model B for the implementation guide.

The Discord bot never talks to Docker or Hetzner directly — it calls this API. Switching backends is a one-line `.env` change: `MODE=local` → `MODE=hetzner` and restart. No bot code changes.

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

Requires Docker to be reachable via `docker compose` from the repo root (Docker Desktop on Windows/macOS, Docker Engine on Linux). Full local-dev walkthrough: [../docs/LOCAL-DEV.md](../docs/LOCAL-DEV.md).

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

## Deploying to a cloud host

Two deployment models documented in [../docs/DEPLOY-HETZNER.md](../docs/DEPLOY-HETZNER.md):

- **Always-on VPS** — run this control-API + a Docker container on one Hetzner VPS. `MODE=local` on the VPS. No code changes needed.
- **On-demand VPS** — a tiny controller runs this control-API in `MODE=hetzner`, provisioning MC VPS on demand. Requires implementing the three methods in `backends/hetzner.py`.
