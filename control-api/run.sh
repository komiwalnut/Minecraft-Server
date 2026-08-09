#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .venv/bin/activate ]]; then
    echo "No .venv found. Run these once first:"
    echo "  python -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

exec uvicorn server:app --host 127.0.0.1 --port 8080 --reload
