#!/bin/bash
# Zoom Meeting Bot ビルドスクリプト
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=========================================="
echo "  🔨 Zoom Meeting Bot ビルド"
echo "=========================================="

cd "$BACKEND_DIR"

# Dockerイメージビルド
echo "[Build] Dockerイメージをビルド中..."
docker build -f Dockerfile.bot -t tech-notta-bot:latest .

echo ""
echo "=========================================="
echo "  ✅ ビルド完了!"
echo "=========================================="
echo ""
echo "使用方法:"
echo "  docker run --rm \\"
echo "    -e JWT_TOKEN=\"your_jwt_token\" \\"
echo "    -e MEETING_NUMBER=\"123456789\" \\"
echo "    -e PASSWORD=\"password\" \\"
echo "    -e BOT_NAME=\"Tech Bot\" \\"
echo "    tech-notta-bot:latest"
echo ""
