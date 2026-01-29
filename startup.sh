#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
exec gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind "0.0.0.0:${PORT}"
