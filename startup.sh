#!/usr/bin/env bash
set -euo pipefail

WWWROOT=/home/site/wwwroot

# /app シンボリックリンク作成（browser bot の絶対パス参照を解決するため）
# /app がディレクトリとして存在する場合も対応
rm -rf /app 2>/dev/null || true
ln -sfn "$WWWROOT" /app 2>/dev/null || echo "WARNING: Could not create /app symlink."

# Bot スクリプトを entrypoint.py が期待する絶対パス (/app/*.py, /app/*.sh) にコピー
for f in realtime_transcriber.py upload_workflow.py; do
  cp -f "$WWWROOT/app/bot_runner/$f" "$WWWROOT/$f" 2>/dev/null || true
done
for f in setup-pulseaudio.sh audio_capture.sh; do
  cp -f "$WWWROOT/app/bot_runner/$f" "$WWWROOT/$f" 2>/dev/null || true
  chmod +x "$WWWROOT/$f" 2>/dev/null || true
  sed -i 's/\r//' "$WWWROOT/$f" 2>/dev/null || true
done

# Chrome 用フェイクメディアファイル生成
python3 -c 'w,h=640,360; uv=(w//2)*(h//2); f=open("'"$WWWROOT"'/black.y4m","wb"); f.write(("YUV4MPEG2 W"+str(w)+" H"+str(h)+" F30:1 Ip A0:0 C420\n").encode()); f.write(b"FRAME\n"); f.write(bytes(w*h)); f.write(bytes([128]*uv)); f.write(bytes([128]*uv)); f.close()' 2>/dev/null || true
python3 -c 'import wave; f=wave.open("'"$WWWROOT"'/silent.wav","wb"); f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(bytes(16000*2)); f.close()' 2>/dev/null || true
mkdir -p "$WWWROOT/recordings"

# Playwright Chromium インストール（/home/playwright/ に永続保存 → 再起動時はスキップ）
export PLAYWRIGHT_BROWSERS_PATH=/home/playwright
if [ ! -d "/home/playwright" ] || [ -z "$(ls -A /home/playwright 2>/dev/null)" ]; then
  echo "Installing Playwright Chromium (first time)..."
  playwright install chromium 2>/dev/null || echo "WARNING: Playwright Chromium install failed."
fi

# --- 重いパッケージインストールをバックグラウンドで実行 ---
# gunicorn の起動を遅延させないため、apt-get は gunicorn 起動後に実行
# Bot dispatch 時に必要なパッケージが揃っていなければエラーになるが、
# 通常は gunicorn 起動〜初回 Bot dispatch までに十分間に合う
_install_system_deps() {
  echo "Background: installing system packages (ffmpeg, xvfb, pulseaudio)..."
  apt-get update -qq 2>/dev/null || true
  apt-get install -y -qq ffmpeg xvfb pulseaudio pulseaudio-utils libasound2-plugins 2>/dev/null || true
  playwright install-deps chromium 2>/dev/null || true
  echo "Background: system packages installed."
}
_install_system_deps &

PORT="${PORT:-8000}"
exec gunicorn -k uvicorn.workers.UvicornWorker app.main:app \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --timeout 300 \
  --graceful-timeout 30
