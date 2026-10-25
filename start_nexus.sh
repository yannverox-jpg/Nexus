#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Start the canonical Nexus FastAPI runtime; do not launch the legacy Streamlit dashboard.
if [[ -f venv/bin/activate ]]; then
  source venv/bin/activate
fi

: "${PORT:=8000}"
exec uvicorn nexus_services.nexus_api_server:app --host 0.0.0.0 --port "$PORT"
