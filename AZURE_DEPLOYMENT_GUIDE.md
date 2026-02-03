# Azure App Service デプロイガイド

## 📋 デプロイ前のチェックリスト

### 1. ローカルでの確認
- ✅ すべての機能が正常に動作することを確認
- ✅ テストが成功することを確認
- ✅ requirements.txt が最新であることを確認

### 2. Git へのコミット
```bash
git add .
git commit -m "feat: チャット機能とSlack通知機能を追加"
git push origin main
```

---

## 🔧 Azure App Service の設定

### 必須：環境変数の追加

Azure Portal → App Service → 構成 → アプリケーション設定 で以下を追加：

#### Slack 関連（新規追加）

| 名前 | 値 | 説明 |
|---|---|---|
| `SLACK_BOT_TOKEN` | `xoxb-...` | Slack Bot User OAuth Token |
| `SLACK_CHANNEL_ID` | `C...` | 通知先のSlackチャンネルID |
| `SLACK_SIGNING_SECRET` | `...` | Slack Signing Secret（将来の拡張用） |

#### 既存の環境変数（確認）

以下が設定されていることを確認：

**必須**
- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_STORAGE_CONTAINER_NAME`
- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`
- `AZURE_SPEECH_API_VERSION`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT_NAME`
- `AZURE_OPENAI_API_VERSION`
- `CORS_ORIGINS`

**任意**
- `AZURE_SPEECH_ENDPOINT`
- `NOTION_API_KEY`
- `NOTION_DATABASE_ID`
- `MAX_FILE_SIZE_MB`
- `DATABASE_URL`

---

## 📦 依存パッケージの確認

`requirements.txt` に以下が含まれていることを確認：

```txt
slack-sdk==3.27.0
```

GitHub Actions が自動的にインストールします。

---

## 🗄️ データベースのマイグレーション

新しいテーブル（`chat_sessions`, `chat_messages`）が自動的に作成されます。

### 自動マイグレーション

アプリ起動時に `init_db()` が実行され、以下が自動的に行われます：

1. 既存のテーブルはそのまま保持
2. 新しいテーブル（`chat_sessions`, `chat_messages`）を作成
3. `jobs` テーブルにリレーションを追加（既存データに影響なし）

### 手動確認（オプション）

Azure Portal → App Service → SSH で接続して確認：

```bash
# Pythonコンソールを起動
python

# データベース確認
from app.database import engine
from sqlalchemy import inspect
inspector = inspect(engine)
print(inspector.get_table_names())
# ['jobs', 'chat_sessions', 'chat_messages'] が表示されればOK
```

---

## 🚀 デプロイ手順

### 1. GitHub へプッシュ

```bash
cd C:\Users\shohey sasaki\Documents\202510_techSWAT\20260124_tech0notta\backend_clone

# 変更を確認
git status

# すべての変更をステージング
git add .

# コミット
git commit -m "feat: チャット機能とSlack通知機能を追加

- 対話型リライト（チャット）機能を実装
- 議事録承認後のSlack通知機能を実装
- README.mdを更新
- 既存機能への影響なし（後方互換性を保持）"

# プッシュ
git push origin main
```

### 2. GitHub Actions の確認

1. GitHub リポジトリを開く
2. 「Actions」タブをクリック
3. 最新のワークフローが実行されていることを確認
4. ✅ すべてのステップが成功することを確認

### 3. Azure Portal で環境変数を追加

1. **Azure Portal にログイン**
   - https://portal.azure.com

2. **App Service を開く**
   - リソースグループ → App Service を選択

3. **構成を開く**
   - 左メニュー → 設定 → 構成

4. **新しいアプリケーション設定を追加**
   - 「+ 新しいアプリケーション設定」をクリック
   - 以下を追加：

   ```
   名前: SLACK_BOT_TOKEN
   値: xoxb-your-actual-token
   ```

   ```
   名前: SLACK_CHANNEL_ID
   値: C1234567890
   ```

   ```
   名前: SLACK_SIGNING_SECRET
   値: your-signing-secret
   ```

5. **保存**
   - 「保存」をクリック
   - 「続行」をクリック（アプリが再起動されます）

### 4. デプロイの確認

1. **App Service の URL を開く**
   - `https://your-app-name.azurewebsites.net`

2. **Swagger UI を確認**
   - `https://your-app-name.azurewebsites.net/docs`

3. **新しいエンドポイントが表示されることを確認**
   - `POST /api/chat/sessions`
   - `POST /api/chat/sessions/{session_id}/messages`
   - `GET /api/chat/sessions/{session_id}/messages`
   - `GET /api/chat/sessions`
   - `POST /api/approve`

4. **ログを確認**
   - Azure Portal → App Service → ログストリーム
   - エラーがないことを確認

---

## 🧪 デプロイ後のテスト

### 1. 基本的な動作確認

Swagger UI で以下をテスト：

1. **既存機能の確認**
   - `POST /api/upload` → ファイルアップロード
   - `POST /api/transcribe` → 文字起こし
   - `POST /api/summarize` → 要約生成

2. **新機能の確認**
   - `POST /api/chat/sessions` → セッション作成
   - `POST /api/chat/sessions/{session_id}/messages` → メッセージ送信
   - `POST /api/approve` → 承認・Slack通知

### 2. Slack 通知のテスト

1. 議事録を作成（upload → transcribe → summarize）
2. `POST /api/approve` で承認
3. Slack チャンネルに通知が投稿されることを確認

---

## 🔍 トラブルシューティング

### エラー: "No module named 'slack_sdk'"

**原因**: requirements.txt が更新されていない、またはデプロイが失敗

**解決方法**:
1. requirements.txt に `slack-sdk==3.27.0` が含まれているか確認
2. GitHub Actions のログを確認
3. App Service を再起動

### エラー: "SLACK_BOT_TOKEN not configured"

**原因**: 環境変数が設定されていない

**解決方法**:
1. Azure Portal → App Service → 構成 で環境変数を確認
2. 環境変数を追加して保存
3. App Service を再起動

### エラー: "channel_not_found"

**原因**: SLACK_CHANNEL_ID が間違っている、または Bot がチャンネルに招待されていない

**解決方法**:
1. Slack チャンネルの Channel ID を再確認
2. Slack チャンネルで `/invite @your-bot-name` を実行
3. 環境変数を更新

### データベースエラー

**原因**: マイグレーションが失敗

**解決方法**:
1. App Service → SSH で接続
2. `python -c "from app.database import init_db; init_db()"` を実行
3. エラーメッセージを確認

---

## 📊 デプロイ後の確認項目

### 必須確認

- ✅ GitHub Actions が成功
- ✅ App Service が起動
- ✅ Swagger UI が表示される
- ✅ 既存のエンドポイントが動作
- ✅ 新しいエンドポイントが表示される
- ✅ 環境変数が設定されている

### オプション確認

- ✅ Slack 通知が動作
- ✅ チャット機能が動作
- ✅ データベースに新しいテーブルが作成されている
- ✅ ログにエラーがない

---

## 🔒 セキュリティチェック

### 環境変数の確認

- ✅ `.env` ファイルが Git にコミットされていない（`.gitignore` に含まれている）
- ✅ Slack Bot Token が安全に管理されている
- ✅ Azure Portal の環境変数のみに機密情報が保存されている

### アクセス制御

- ✅ Slack Bot に必要最小限の権限のみが付与されている（`chat:write`）
- ✅ CORS 設定が適切（必要なオリジンのみ許可）

---

## 📝 ロールバック手順

問題が発生した場合のロールバック：

### 1. Git でロールバック

```bash
# 前のコミットに戻る
git revert HEAD
git push origin main
```

### 2. Azure Portal でロールバック

1. App Service → デプロイセンター
2. 「ログ」タブで前のデプロイを選択
3. 「再デプロイ」をクリック

---

## 🎯 まとめ

### デプロイに必要な作業

1. ✅ GitHub へプッシュ
2. ✅ Azure Portal で環境変数を追加（Slack関連）
3. ✅ デプロイの確認
4. ✅ 動作テスト

### 追加の対応は不要

- ❌ データベースの手動マイグレーション（自動実行）
- ❌ 依存パッケージの手動インストール（GitHub Actions が実行）
- ❌ 既存データの移行（既存データはそのまま保持）

---

以上でデプロイ完了です！🚀
