# Meeting Notes Backend API

FastAPIを使った議事録アプリケーションのバックエンドAPI

## 機能

- 音声ファイルのアップロード (Azure Blob Storage)
- 音声の文字起こし (Azure AI Speech Service)
- GPT-4oによる要約生成 (Azure OpenAI)
- Notionへの議事録保存 (Notion API)
- ジョブ管理 (PostgreSQL)

## セットアップ

### 1. 環境変数の設定

`.env.example`をコピーして`.env`を作成し、必要な情報を入力してください。

```bash
cp .env.example .env
```

### 2. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 3. データベースのセットアップ

PostgreSQLが起動していることを確認してください。

### 4. サーバーの起動

```bash
uvicorn app.main:app --reload
```

サーバーは `http://localhost:8000` で起動します。

## API エンドポイント

### POST /api/upload
音声ファイルをアップロード

```bash
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@meeting.wav"
```

### POST /api/transcribe
音声を文字起こし

```bash
curl -X POST "http://localhost:8000/api/transcribe" \
  -H "Content-Type: application/json" \
  -d '{"job_id": "your-job-id"}'
```

### POST /api/summarize
文字起こしを要約

```bash
curl -X POST "http://localhost:8000/api/summarize" \
  -H "Content-Type: application/json" \
  -d '{"job_id": "your-job-id"}'
```

### POST /api/notion/create
Notionページを作成

```bash
curl -X POST "http://localhost:8000/api/notion/create" \
  -H "Content-Type: application/json" \
  -d '{"job_id": "your-job-id", "title": "会議タイトル"}'
```

### GET /api/jobs/{job_id}
ジョブのステータス確認

```bash
curl "http://localhost:8000/api/jobs/{job_id}"
```

## Docker

### ビルド

```bash
docker build -t meeting-notes-api .
```

### 実行

```bash
docker run -p 8000:8000 --env-file .env meeting-notes-api
```

## プロジェクト構造

```
backend/
├── app/
│   ├── main.py              # FastAPI entry
│   ├── config.py            # 環境変数
│   ├── database.py          # DB接続
│   ├── models/
│   │   └── job.py           # Jobモデル
│   ├── routers/
│   │   ├── upload.py        # アップロード
│   │   ├── transcribe.py    # 文字起こし
│   │   ├── summarize.py     # 要約
│   │   └── notion.py        # Notion連携
│   └── services/
│       ├── azure_speech.py
│       ├── azure_openai.py
│       ├── blob_storage.py
│       └── notion_client.py
├── requirements.txt
├── .env.example
└── Dockerfile
```

## ジョブステータス

- `pending`: 初期状態
- `uploading`: アップロード中
- `uploaded`: アップロード完了
- `transcribing`: 文字起こし中
- `transcribed`: 文字起こし完了
- `summarizing`: 要約生成中
- `summarized`: 要約完了
- `creating_notion`: Notion作成中
- `completed`: 完了
- `failed`: エラー

## ライセンス

MIT
