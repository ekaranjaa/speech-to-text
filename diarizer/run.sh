#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# Load diarizer/.env if present (host-native config incl. HF_TOKEN).
if [ -f .env ]; then set -a; . ./.env; set +a; fi
exec uvicorn app.main:create_app --factory --host 127.0.0.1 --port "${DIARIZER_PORT:-8090}"
