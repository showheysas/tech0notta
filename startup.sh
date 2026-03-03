#!/usr/bin/env bash
set -euo pipefail

# Bot は ACA Job コンテナで実行されるため、App Service には
# Xvfb, PulseAudio, Playwright 等のシステムパッケージは不要

PORT="${PORT:-8000}"
gunicorn -k uvicorn.workers.UvicornWorker app.main:app \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --timeout 300 \
  --graceful-timeout 30
