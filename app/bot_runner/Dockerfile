# Tech Notta Bot Runner
# Zoom Meeting SDK Linux用のDockerコンテナ

FROM ubuntu:22.04

# 非対話モード設定
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Tokyo

# 基本パッケージインストール
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    python3 \
    python3-pip \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Zoom Meeting SDK依存ライブラリ
RUN apt-get update && apt-get install -y --no-install-recommends --no-install-suggests \
    libx11-xcb1 \
    libxcb-xfixes0 \
    libxcb-shape0 \
    libxcb-shm0 \
    libxcb-randr0 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-xtest0 \
    libdbus-1-3 \
    libglib2.0-0 \
    libgbm1 \
    libxfixes3 \
    libgl1 \
    libdrm2 \
    libgssapi-krb5-2 \
    && rm -rf /var/lib/apt/lists/*

# PulseAudio（仮想サウンドカード用）
RUN apt-get update && apt-get install -y \
    pulseaudio \
    pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

# CURL関連
RUN apt-get update && apt-get install -y \
    libcurl4-openssl-dev \
    openssl \
    ca-certificates \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Python依存パッケージ
RUN pip3 install --no-cache-dir \
    httpx \
    python-dotenv

# 作業ディレクトリ
WORKDIR /app

# 設定ファイル用ディレクトリ
RUN mkdir -p /root/.config/zoomus

# PulseAudio設定
COPY setup-pulseaudio.sh /app/
RUN chmod +x /app/setup-pulseaudio.sh

# Bot Runnerスクリプト
COPY entrypoint.py /app/
COPY config_generator.py /app/

# Zoom Meeting SDK配置用ディレクトリ
# ※ SDKはZoom Marketplaceからダウンロード後に配置
RUN mkdir -p /app/sdk

# 録音ファイル保存用
RUN mkdir -p /app/recordings

# エントリポイント
ENTRYPOINT ["python3", "/app/entrypoint.py"]
