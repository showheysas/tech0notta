#!/bin/bash
set -e

# ACA App (minReplicas=1) 用エントリポイント
# Xvfb + PulseAudio を起動した状態で HTTP サーバーを常時待機させる

# Xvfb（仮想ディスプレイ）とPulseAudioを並列起動
Xvfb :99 -screen 0 1280x720x24 > /dev/null 2>&1 &
export DISPLAY=:99
/app/setup-pulseaudio.sh &
PULSE_PID=$!

# Xvfb の準備完了を能動的にチェック
for i in $(seq 1 20); do
  if xdpyinfo -display :99 > /dev/null 2>&1; then
    break
  fi
  sleep 0.05
done

# PulseAudio セットアップ完了を待つ
wait $PULSE_PID 2>/dev/null || true

# フェイクメディアパス
export FAKE_VIDEO_PATH="${FAKE_VIDEO_PATH:-/app/black.y4m}"
export FAKE_AUDIO_PATH="${FAKE_AUDIO_PATH:-/app/silent.wav}"

# Playwright ブラウザパス
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/home/botuser/pw-browsers}"

# Python パスに /app/ を追加
export PYTHONPATH="/app:${PYTHONPATH:-}"

echo "=== ACA App Bot Server 起動 (Xvfb + PulseAudio 準備完了) ==="

exec python3 /app/bot_http_server.py
