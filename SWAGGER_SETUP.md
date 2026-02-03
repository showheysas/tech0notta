# Swagger UI でチャット機能を確認する手順

## 📋 前提条件

1. Python 3.11以上がインストールされていること
2. 必要な環境変数が設定されていること（`.env`ファイル）

---

## 🚀 起動手順

### 1. ディレクトリ移動
```powershell
cd C:\Users\shohey sasaki\Documents\202510_techSWAT\20260124_tech0notta\backend_clone
```

### 2. 仮想環境の作成（初回のみ）
```powershell
python -m venv venv
```

### 3. 仮想環境の有効化
```powershell
.\venv\Scripts\Activate.ps1
```

**注意**: PowerShellの実行ポリシーでエラーが出る場合は、以下を実行：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 4. 依存パッケージのインストール（初回のみ）
```powershell
pip install -r requirements.txt
```

### 5. 環境変数の設定

`.env`ファイルが存在するか確認：
```powershell
dir .env
```

存在しない場合は、`.env.example`をコピーして作成：
```powershell
copy .env.example .env
```

`.env`ファイルを編集して、以下の値を設定：
```env
# Azure OpenAI
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Database
DATABASE_URL=sqlite:///./meeting_notes.db

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

### 6. データベースの初期化（初回のみ）
サーバーを起動すると自動的にテーブルが作成されます。

### 7. サーバー起動
```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**オプション説明**:
- `--reload`: コード変更時に自動再起動
- `--host 0.0.0.0`: すべてのネットワークインターフェースでリッスン
- `--port 8000`: ポート8000で起動

### 8. Swagger UIにアクセス
ブラウザで以下のURLを開く：
```
http://localhost:8000/docs
```

---

## 🧪 チャット機能のテスト手順

### Step 1: テスト用のJobを作成

まず、要約済みのJobが必要です。既存のJobがない場合は、以下の方法で作成：

#### 方法A: 既存のJobを確認
```powershell
# 別のターミナルで実行
python check_db.py
```

#### 方法B: テストスクリプトでJobを作成
```powershell
# 別のターミナルで実行
python test_chat_implementation.py
```

このスクリプトは自動的にテスト用のJobとセッションを作成します。

### Step 2: Swagger UIでAPIをテスト

#### 2-1. チャットセッション作成

1. Swagger UI (`http://localhost:8000/docs`) を開く
2. `POST /api/chat/sessions` を展開
3. 「Try it out」をクリック
4. Request bodyに以下を入力：
```json
{
  "job_id": "your-job-id-here"
}
```
5. 「Execute」をクリック
6. レスポンスから `session_id` をコピー

**期待されるレスポンス**:
```json
{
  "session_id": "abc-123-xyz",
  "job_id": "your-job-id-here",
  "created_at": "2026-02-02T10:00:00Z",
  "updated_at": null
}
```

#### 2-2. メッセージ送信（非ストリーミング）

1. `POST /api/chat/sessions/{session_id}/messages` を展開
2. 「Try it out」をクリック
3. `session_id` に先ほどコピーしたIDを入力
4. Request bodyに以下を入力：
```json
{
  "message": "要約を半分の長さにしてください",
  "streaming": false
}
```
5. 「Execute」をクリック

**期待されるレスポンス**:
```json
{
  "message_id": "msg-001",
  "role": "assistant",
  "content": "## 概要\n修正された議事録の内容...",
  "created_at": "2026-02-02T10:00:30Z"
}
```

#### 2-3. チャット履歴取得

1. `GET /api/chat/sessions/{session_id}/messages` を展開
2. 「Try it out」をクリック
3. `session_id` を入力
4. 「Execute」をクリック

**期待されるレスポンス**:
```json
{
  "session_id": "abc-123-xyz",
  "job_id": "your-job-id-here",
  "messages": [
    {
      "message_id": "msg-000",
      "role": "user",
      "content": "要約を半分の長さにしてください",
      "created_at": "2026-02-02T10:00:00Z"
    },
    {
      "message_id": "msg-001",
      "role": "assistant",
      "content": "## 概要\n修正された議事録...",
      "created_at": "2026-02-02T10:00:30Z"
    }
  ]
}
```

#### 2-4. セッション一覧取得

1. `GET /api/chat/sessions` を展開
2. 「Try it out」をクリック
3. `job_id` パラメータに値を入力（オプション）
4. 「Execute」をクリック

**期待されるレスポンス**:
```json
{
  "sessions": [
    {
      "session_id": "abc-123-xyz",
      "job_id": "your-job-id-here",
      "message_count": 2,
      "created_at": "2026-02-02T10:00:00Z",
      "updated_at": "2026-02-02T10:00:30Z"
    }
  ]
}
```

#### 2-5. メッセージ送信（ストリーミング）

**注意**: Swagger UIではストリーミングレスポンスの確認が難しいため、curlまたはPostmanを使用することを推奨します。

```powershell
# PowerShellで実行
curl -X POST "http://localhost:8000/api/chat/sessions/{session_id}/messages" `
  -H "Content-Type: application/json" `
  -d '{\"message\": \"決定事項を強調してください\", \"streaming\": true}'
```

---

## 🔍 トラブルシューティング

### エラー: "Job not found"
- `job_id` が正しいか確認
- データベースにJobが存在するか確認: `python check_db.py`

### エラー: "Summary not generated yet"
- Jobのステータスが `SUMMARIZED` または `COMPLETED` であることを確認
- 必要に応じて `/api/summarize` エンドポイントで要約を生成

### エラー: "Session not found"
- `session_id` が正しいか確認
- セッションが作成されているか確認: `GET /api/chat/sessions`

### エラー: Azure OpenAI API関連
- `.env` ファイルの設定を確認
- API キーが有効か確認
- デプロイメント名が正しいか確認

### サーバーが起動しない
```powershell
# ポート8000が使用中の場合、別のポートを使用
python -m uvicorn app.main:app --reload --port 8001
```

### 仮想環境が有効化できない
```powershell
# 実行ポリシーを変更
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 再度有効化を試す
.\venv\Scripts\Activate.ps1
```

---

## 📊 データベースの確認

### SQLiteデータベースを直接確認
```powershell
# SQLiteがインストールされている場合
sqlite3 meeting_notes.db

# テーブル一覧
.tables

# chat_sessionsテーブルの内容
SELECT * FROM chat_sessions;

# chat_messagesテーブルの内容
SELECT * FROM chat_messages;

# 終了
.quit
```

### Pythonスクリプトで確認
```powershell
python check_db.py
```

---

## 🛑 サーバーの停止

ターミナルで `Ctrl + C` を押す

---

## 📝 テストシナリオ例

### シナリオ1: 議事録を段階的に修正

1. **セッション作成**
   - `POST /api/chat/sessions` で新しいセッションを作成

2. **要約を短くする**
   - メッセージ: "要約を半分の長さにしてください"

3. **箇条書きに変更**
   - メッセージ: "主な議題を箇条書きにしてください"

4. **決定事項を強調**
   - メッセージ: "決定事項のセクションを太字で強調してください"

5. **履歴確認**
   - `GET /api/chat/sessions/{session_id}/messages` で全履歴を確認

### シナリオ2: 複数セッションの管理

1. **複数のセッションを作成**
   - 同じJobに対して複数のセッションを作成

2. **セッション一覧を確認**
   - `GET /api/chat/sessions?job_id={job_id}` で一覧を取得

3. **各セッションで異なる修正を試す**
   - セッションA: 短縮版
   - セッションB: 詳細版
   - セッションC: 箇条書き版

---

## 🎯 確認ポイント

### 機能確認
- ✅ セッションが正常に作成できる
- ✅ メッセージが送信できる
- ✅ AIが適切に応答する
- ✅ 履歴が正しく保存される
- ✅ セッション一覧が取得できる

### エラーハンドリング確認
- ✅ 存在しないJobでセッション作成 → 404エラー
- ✅ 存在しないセッションにメッセージ送信 → 404エラー
- ✅ 空のメッセージ送信 → 400エラー
- ✅ 2000文字を超えるメッセージ → 400エラー

### パフォーマンス確認
- ✅ レスポンス時間が適切（5秒以内）
- ✅ ストリーミングが正常に動作
- ✅ 複数リクエストの同時処理

---

## 📚 参考情報

- FastAPI公式ドキュメント: https://fastapi.tiangolo.com/
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

以上の手順で、チャット機能の実装を確認できます！
