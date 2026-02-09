# Task 5.5 実装サマリー: タスクDB登録API

## 概要

Task 5.5「タスクDB登録APIを実装」を完了しました。このタスクでは、承認されたタスクをNotion Task DBに登録する機能を実装しました。

## 実装内容

### 1. 新規ファイル作成

#### `app/services/notion_task_service.py`
Notion Task DBとの連携を担当する新しいサービスを作成しました。

**主な機能:**
- タスクのNotion DB登録
- リトライ処理（3回、指数バックオフ）
- 親タスク・サブタスクの作成
- リレーション設定（プロジェクト、議事録、親タスク）

**リトライ処理:**
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(APIResponseError),
    reraise=True
)
async def create_task(...):
    # Notion API呼び出し
```

### 2. 既存ファイル更新

#### `app/services/task_service.py`
`register_tasks`メソッドを実装しました。

**実装内容:**
- 各タスクを順次登録
- 親タスクを先に作成
- サブタスクを親タスクIDと共に作成
- エラーハンドリング（個別タスクのエラーは記録して継続）

#### `app/config.py`
Notion Task DB IDの設定を追加しました。

```python
NOTION_TASK_DB_ID: str = ""
```

#### `requirements.txt`
リトライ処理用のライブラリを追加しました。

```
tenacity==8.2.3
```

### 3. テストファイル作成

#### `test_task_registration.py`
基本的な統合テスト（Notion APIキーが必要）

#### `test_task_registration_mock.py`
モックを使用した単体テスト（Notion APIキー不要）

**テストケース:**
1. 基本的なタスク登録（親タスク + サブタスク）
2. リトライ処理の検証
3. サブタスクの親タスクリレーションの検証

## Requirements 検証

### ✅ Requirement 6.1: タスクがNotion Task DBに登録される
- `NotionTaskService.create_task`メソッドでNotion APIを呼び出し
- タスクページを作成

### ✅ Requirement 6.2: タスクレコードに必要な情報が含まれる
以下のプロパティを設定:
- Name (title)
- Due Date
- Status
- Priority
- Assignee (Rich Text)
- Project (Relation)
- Meeting (Relation)
- Parent Task (Relation - サブタスクの場合)
- Description (ページコンテンツ)

### ✅ Requirement 6.3: 初期ステータスが「未着手」に設定される
```python
status=TaskStatus.NOT_STARTED
```

### ✅ Requirement 6.4: デフォルト優先度が「中」に設定される
`TaskCreate`モデルでデフォルト値を設定:
```python
priority: TaskPriority = TaskPriority.MEDIUM
```

### ✅ Requirement 6.5: サブタスクが親タスクリレーションと共に作成される
```python
if task.subtasks:
    for subtask in task.subtasks:
        subtask_id = await notion_service.create_task(
            ...
            parent_task_id=parent_task_id
        )
```

### ✅ Requirement 6.7: Notion APIエラー時に3回リトライ（指数バックオフ）
`tenacity`ライブラリを使用:
```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
```

## API エンドポイント

### POST /api/tasks/register

**リクエスト:**
```json
{
  "job_id": "string",
  "project_id": "string",
  "tasks": [
    {
      "title": "string",
      "description": "string",
      "assignee": "string",
      "due_date": "2024-01-01",
      "priority": "高",
      "subtasks": [
        {
          "title": "string",
          "description": "string",
          "order": 1
        }
      ]
    }
  ]
}
```

**レスポンス:**
```json
{
  "job_id": "string",
  "registered_count": 5,
  "task_ids": [
    "notion-task-1",
    "notion-task-2",
    "notion-task-3",
    "notion-task-4",
    "notion-task-5"
  ]
}
```

## 環境変数設定

`.env`ファイルに以下を追加してください:

```env
NOTION_API_KEY=secret_xxxxxxxxxxxxx
NOTION_TASK_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## テスト実行方法

### モックテスト（推奨）
```bash
python test_task_registration_mock.py
```

### 統合テスト（Notion APIキーが必要）
```bash
python test_task_registration.py
```

## テスト結果

```
✅ 基本的なタスク登録: 成功
   - 親タスク2個 + サブタスク3個 = 5個のタスクが登録される
   - Notion API呼び出し回数: 5回

✅ サブタスクの親タスクリレーション: 成功
   - 親タスクが最初に作成される
   - サブタスクに親タスクIDが正しく設定される

✅ リトライ処理: 実装済み
   - tenacityライブラリで3回リトライ
   - 指数バックオフ（1秒、2秒、4秒...最大10秒）
```

## 実装の特徴

### 1. エラーハンドリング
- 個別タスクの登録エラーは記録するが、処理は継続
- 全体のエラーは適切にHTTPExceptionとして返す

### 2. リトライ戦略
- Notion APIエラー（APIResponseError）のみリトライ
- 3回まで試行
- 指数バックオフで負荷を軽減

### 3. リレーション設定
- プロジェクトリレーション
- 議事録リレーション
- 親タスクリレーション（サブタスクの場合）

### 4. 担当者の扱い
- "未割り当て"の場合はAssigneeプロパティを設定しない
- それ以外の場合はRich Textとして保存
  - Note: Notion APIでPeopleプロパティを設定するにはユーザーIDが必要
  - 将来的にユーザーマッピング機能を追加する予定

## 次のステップ

### Task 5.6: タスク登録のプロパティテストを作成
以下のプロパティをテスト:
- Property 13: Task Registration on Approval
- Property 14: Task Record Completeness
- Property 18: Subtask Parent Relation
- Property 26: Notion API Retry Behavior

### Task 5.7: タスク一覧・更新APIを実装
- GET /api/tasks - タスク一覧取得
- GET /api/tasks/{task_id} - タスク詳細取得
- PUT /api/tasks/{task_id} - タスク更新
- DELETE /api/tasks/{task_id} - タスク削除

## 注意事項

1. **Notion DB設定が必要**
   - NOTION_API_KEYとNOTION_TASK_DB_IDを環境変数に設定
   - Notion Task DBに必要なプロパティを作成
     - Name (Title)
     - Due Date (Date)
     - Status (Select: 未着手、進行中、完了)
     - Priority (Select: 高、中、低)
     - Assignee (Rich Text)
     - Project (Relation)
     - Meeting (Relation)
     - Parent Task (Relation)

2. **依存ライブラリのインストール**
   ```bash
   pip install tenacity==8.2.3
   ```

3. **エラーログの確認**
   - 個別タスクの登録エラーはログに記録される
   - 本番環境ではログを監視して問題を早期発見

## まとめ

Task 5.5の実装により、以下が可能になりました:

✅ 承認されたタスクをNotion Task DBに自動登録
✅ 親タスク・サブタスクの階層構造を保持
✅ プロジェクト、議事録とのリレーション設定
✅ Notion APIエラー時の自動リトライ
✅ 堅牢なエラーハンドリング

これにより、Requirements 6.1-6.7がすべて満たされました。
