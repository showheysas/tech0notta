#!/bin/bash
# PulseAudio設定スクリプト
# ヘッドレス環境で仮想サウンドカードを設定

echo "🔊 PulseAudio設定を開始..."

# PulseAudioサービス開始
pulseaudio --start --exit-idle-time=-1 2>/dev/null || true

# 仮想スピーカー（シンク）作成
pactl load-module module-null-sink sink_name=virtual_speaker sink_properties=device.description="Virtual_Speaker" 2>/dev/null || true

# 仮想マイク（ソース）作成
pactl load-module module-null-sink sink_name=virtual_mic sink_properties=device.description="Virtual_Mic" 2>/dev/null || true
pactl load-module module-virtual-source source_name=virtual_mic_source master=virtual_mic.monitor 2>/dev/null || true

# デフォルトシンクをvirtual_speakerに設定
# ChromeがPulseAudioに音声を出力する際にvirtual_speakerに流れるようにする
pactl set-default-sink virtual_speaker 2>/dev/null || true

# デフォルトソースをvirtual_speaker.monitorに設定
# Azure Speech SDKがuse_default_microphone=Trueで使用するため重要
pactl set-default-source virtual_speaker.monitor 2>/dev/null || true

# ALSA → PulseAudio ルーティング設定
# Azure Speech SDK（ALSA経由）がPulseAudioのvirtual_speaker.monitorを使えるようにする
cat > ~/.asoundrc << EOF
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
EOF

# Zoom用設定ファイル作成
mkdir -p ~/.config/zoomus
cat > ~/.config/zoomus/zoomus.conf << EOF
[General]
system.audio.type=default
EOF

echo "✅ PulseAudio設定完了"

# 設定確認
echo "📊 オーディオデバイス一覧:"
pactl list short sinks 2>/dev/null || echo "  (sinks not available)"
pactl list short sources 2>/dev/null || echo "  (sources not available)"
