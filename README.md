# Tech0 Notta MVP Backend API

FastAPI で音声ファイルのアップロード、文字起こし、要約、Notion 連携、対話型リライト、Slack 通知を行うバックエンドです。  

## デプロイ

- デプロイ先: Azure App Service (Linux)
- GitHub Actions で継続デプロイ
- Startup Command: `bash startup.sh`

## 必要な環境変数（App Service > 構成）

必須:
- AZURE_STORAGE_CONNECTION_STRING
- AZURE_STORAGE_CONTAINER_NAME
- AZURE_SPEECH_KEY
- AZURE_SPEECH_REGION
- AZURE_SPEECH_API_VERSION
- AZURE_OPENAI_API_KEY
- AZURE_OPENAI_ENDPOINT
- AZURE_OPENAI_DEPLOYMENT_NAME
- AZURE_OPENAI_API_VERSION
- CORS_ORIGINS

任意:
- AZURE_SPEECH_ENDPOINT
- NOTION_API_KEY
- NOTION_DATABASE_ID
- SLACK_BOT_TOKEN
- SLACK_CHANNEL_ID
- SLACK_SIGNING_SECRET
- MAX_FILE_SIZE_MB
- DATABASE_URL

## API

### POST /api/upload
音声ファイルをアップロードします。

- 入力（multipart/form-data）
  - file: 音声ファイル（mp3 / wav など）
- 出力（JSON）
  - job_id: string
  - status: string
  - filename: string
  - blob_name: string
  - blob_url: string
  - message: string

### POST /api/transcribe（非同期）
文字起こしジョブを開始します。すぐに `job_id` が返ります。

- 入力（JSON）
  - job_id: string
- 出力（JSON）
  - job_id: string
  - status: "transcribing"
  - transcription_job_id: string
  - message: string

### GET /api/transcribe/status
文字起こしの進行状況・結果を取得します。

- 入力（query）
  - job_id: string
- 出力（JSON）
  - 進行中: {"job_id","status","batch_status"}
  - 成功: {"job_id","status","transcription"}
  - 失敗: {"job_id","status","error_message"}

### POST /api/summarize
要約を生成します。`template_prompt` を渡すと議事録テンプレートを指定できます。

- 入力（JSON）
  - job_id: string
  - template_prompt: string | null
- 出力（JSON）
  - job_id: string
  - status: "summarized"
  - summary: string
  - message: string

### POST /api/notion/create
Notion に議事録ページを作成します。

- 入力（JSON）
  - job_id: string
  - title: string
- 出力（JSON）
  - job_id: string
  - status: string
  - notion_page_id: string
  - notion_page_url: string
  - message: string

### GET /api/jobs/{job_id}
ジョブの状態を確認します。

- 入力（path）
  - job_id: string
- 出力（JSON）
  - job_id: string
  - status: string
  - transcription: string | null
  - summary: string | null
  - notion_page_id: string | null
  - notion_page_url: string | null
  - error_message: string | null

### POST /api/chat/sessions
チャットセッションを作成します。

- 入力（JSON）
  - job_id: string
- 出力（JSON）
  - session_id: string
  - job_id: string
  - created_at: string
  - updated_at: string | null

### POST /api/chat/sessions/{session_id}/messages
チャットメッセージを送信して議事録をリライトします。

- 入力（JSON）
  - message: string
  - streaming: boolean
- 出力（JSON / ストリーミング）
  - 非ストリーミング: {"message_id","role","content","created_at"}
  - ストリーミング: Server-Sent Events 形式

### GET /api/chat/sessions/{session_id}/messages
チャット履歴を取得します。

- 入力（path）
  - session_id: string
- 出力（JSON）
  - session_id: string
  - job_id: string
  - messages: array

### GET /api/chat/sessions
セッション一覧を取得します。

- 入力（query）
  - job_id: string | null
- 出力（JSON）
  - sessions: array

### POST /api/approve
議事録を承認して Slack に通知します。

- 入力（JSON）
  - job_id: string
- 出力（JSON）
  - job_id: string
  - status: "completed"
  - message: string
  - slack_posted: boolean

## 502 対策（長時間処理）

Batch 文字起こしは時間がかかるため、非同期 API を使用してください。  
必要に応じて App Service のアプリ設定に以下を追加します。

```
GUNICORN_CMD_ARGS=--timeout 900 --workers 1 --graceful-timeout 30
```

## プロジェクト構成

```
backend/
├── app/
│   ├── main.py              # FastAPI entry
│   ├── config.py            # 環境変数
│   ├── database.py          # DB接続
│   ├── models/
│   │   ├── job.py           # Jobモデル
│   │   └── chat.py          # Chatモデル
│   ├── routers/
│   │   ├── upload.py        # アップロード
│   │   ├── transcribe.py    # 文字起こし
│   │   ├── summarize.py     # 要約
│   │   ├── notion.py        # Notion連携
│   │   ├── chat.py          # チャット機能
│   │   └── approval.py      # 承認・Slack通知
│   ├── services/
│   │   ├── azure_speech.py
│   │   ├── azure_openai.py
│   │   ├── blob_storage.py
│   │   ├── notion_client.py
│   │   ├── chat_service.py  # チャットサービス
│   │   └── slack_service.py # Slack通知
│   └── schemas/
│       └── chat.py          # Chatスキーマ
├── requirements.txt
├── .env.example
└── Dockerfile
```
