#!/usr/bin/env bash
set -euo pipefail

# FFmpegをインストール（動画から音声を抽出するために必要）
echo "Installing FFmpeg..."
apt-get update -qq && apt-get install -y -qq ffmpeg > /dev/null 2>&1 || echo "FFmpeg installation failed or already installed"

PORT="${PORT:-8000}"
# Longer timeout for batch transcription polling, single worker to reduce memory.
exec gunicorn -k uvicorn.workers.UvicornWorker app.main:app \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --timeout 300 \
  --graceful-timeout 30
