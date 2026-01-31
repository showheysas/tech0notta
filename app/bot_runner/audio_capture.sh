#!/bin/bash
# 音声キャプチャスクリプト
# PulseAudioのvirtual_speaker.monitorから音声を取得してWAVファイルに保存

set -e

OUTPUT_DIR="${OUTPUT_DIR:-/app/recordings}"
SAMPLE_RATE="${SAMPLE_RATE:-16000}"
CHANNELS="${CHANNELS:-1}"
MEETING_ID="${MEETING_NUMBER:-unknown}"

# 出力ディレクトリ作成
mkdir -p "$OUTPUT_DIR"

# ファイル名（タイムスタンプ + ミーティング番号）
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="${OUTPUT_DIR}/meeting_${MEETING_ID}_${TIMESTAMP}.wav"

echo "🎙️ 音声キャプチャ開始"
echo "   出力先: $OUTPUT_FILE"
echo "   サンプルレート: ${SAMPLE_RATE}Hz"
echo "   チャンネル: ${CHANNELS}"
echo ""

# PulseAudioが準備できるまで待機
sleep 3

# virtual_speaker.monitorから録音開始
# parecordは Ctrl+C で停止するまで録音を続ける
parecord \
    --device=virtual_speaker.monitor \
    --file-format=wav \
    --rate=$SAMPLE_RATE \
    --channels=$CHANNELS \
    "$OUTPUT_FILE"

echo "🛑 音声キャプチャ終了"
echo "   保存先: $OUTPUT_FILE"
