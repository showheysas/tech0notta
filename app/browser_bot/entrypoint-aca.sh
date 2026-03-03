#!/bin/bash
set -e

# Xvfb（仮想ディスプレイ）起動
Xvfb :99 -screen 0 1280x720x24 > /dev/null 2>&1 &
export DISPLAY=:99
sleep 1

# PulseAudio + 仮想オーディオ設定
/app/setup-pulseaudio.sh

# フェイクメディアパス（環境変数未設定ならデフォルト）
export FAKE_VIDEO_PATH="${FAKE_VIDEO_PATH:-/app/black.y4m}"
export FAKE_AUDIO_PATH="${FAKE_AUDIO_PATH:-/app/silent.wav}"

# Playwright ブラウザパス
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/home/botuser/.local/share/playwright}"

exec python3 /app/entrypoint.py "$@"
