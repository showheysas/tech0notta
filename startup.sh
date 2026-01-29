#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
# Longer timeout for batch transcription polling, single worker to reduce memory.
exec gunicorn -k uvicorn.workers.UvicornWorker app.main:app \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --timeout 300 \
  --graceful-timeout 30
