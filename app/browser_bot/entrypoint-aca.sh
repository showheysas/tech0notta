#!/bin/bash
set -e

# Xvfb（仮想ディスプレイ）とPulseAudioを並列起動
Xvfb :99 -screen 0 1280x720x24 > /dev/null 2>&1 &
export DISPLAY=:99
/app/setup-pulseaudio.sh &
PULSE_PID=$!

# Xvfb の準備完了を能動的にチェック（sleep 1 の代わり）
for i in $(seq 1 20); do
  if xdpyinfo -display :99 > /dev/null 2>&1; then
    break
  fi
  sleep 0.05
done

# PulseAudio セットアップ完了を待つ
wait $PULSE_PID 2>/dev/null || true

# フェイクメディアパス（環境変数未設定ならデフォルト）
export FAKE_VIDEO_PATH="${FAKE_VIDEO_PATH:-/app/black.y4m}"
export FAKE_AUDIO_PATH="${FAKE_AUDIO_PATH:-/app/silent.wav}"

# Playwright ブラウザパス
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/home/botuser/pw-browsers}"

# Python パスに /app/ を追加（bare import: google_meet_bot, teams_bot 等に必要）
export PYTHONPATH="/app:${PYTHONPATH:-}"

exec python3 /app/entrypoint.py "$@"
