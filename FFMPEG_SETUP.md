# FFmpeg セットアップガイド

動画ファイルから音声を抽出する機能を使用するには、FFmpegのインストールが必要です。

## Windows

### オプション1: Chocolatey（推奨）

```powershell
# Chocolateyがインストールされていない場合
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# FFmpegをインストール
choco install ffmpeg
```

### オプション2: 手動インストール

1. [FFmpeg公式サイト](https://ffmpeg.org/download.html#build-windows)からダウンロード
2. ZIPファイルを解凍（例: `C:\ffmpeg`）
3. 環境変数PATHに追加:
   - `C:\ffmpeg\bin`をシステム環境変数PATHに追加
4. コマンドプロンプトを再起動して確認:
   ```cmd
   ffmpeg -version
   ```

## macOS

### Homebrew（推奨）

```bash
brew install ffmpeg
```

## Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install ffmpeg
```

## 確認

インストール後、以下のコマンドで確認:

```bash
ffmpeg -version
```

正常にインストールされていれば、バージョン情報が表示されます。

## Azure App Service へのデプロイ

Azure App Service（Linux）では、スタートアップスクリプトでFFmpegをインストールします。

`startup.sh`に以下を追加:

```bash
#!/bin/bash

# FFmpegをインストール
apt-get update
apt-get install -y ffmpeg

# Pythonアプリケーションを起動
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
```

または、Dockerfileを使用する場合:

```dockerfile
FROM python:3.11-slim

# FFmpegをインストール
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# アプリケーションのセットアップ
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000"]
```

## トラブルシューティング

### エラー: `ffmpeg: command not found`

- FFmpegがインストールされていないか、PATHが通っていません
- インストール手順を再確認してください

### エラー: `Failed to extract audio`

- 入力ファイルが破損している可能性があります
- サポートされていない動画形式の可能性があります
- FFmpegのログを確認してください

## サポートされている動画形式

- MP4 (`.mp4`)
- MOV (`.mov`)
- AVI (`.avi`)
- WebM (`.webm`)
- MKV (`.mkv`)

## 音声抽出の仕様

- **出力形式**: WAV (PCM 16-bit)
- **サンプリングレート**: 16kHz
- **チャンネル**: モノラル
- **理由**: Azure Speech Serviceに最適化
