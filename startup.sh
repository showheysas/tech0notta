#!/usr/bin/env bash
set -euo pipefail

# FFmpegをインストール（動画から音声を抽出するために必要）
# タイムアウト120秒を設定し、失敗してもアプリ起動をブロックしない
echo "Installing FFmpeg..."
timeout 120 bash -c 'apt-get update -qq 2>/dev/null && apt-get install -y -qq ffmpeg 2>/dev/null' \
  || echo "WARNING: FFmpeg installation skipped (timeout or error). Video-to-audio extraction may not work."

PORT="${PORT:-8000}"
# Longer timeout for batch transcription polling, single worker to reduce memory.
exec gunicorn -k uvicorn.workers.UvicornWorker app.main:app \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --timeout 300 \
  --graceful-timeout 30
