"""
タスク抽出機能のテスト

Task 5.1の実装を検証するための簡易テストスクリプト
"""
import asyncio
from datetime import date
from app.models.task import TaskExtractRequest
from app.services.task_service import get_task_service


async def test_task_extraction():
    """タスク抽出のテスト"""
    
    # テスト用の議事録要約
    test_summary = """
## 概要
プロジェクトXの進捗確認会議を実施しました。

## 主な議題
- 開発進捗の確認
- 次週のリリース準備
- バグ修正の優先順位付け

## 決定事項
- 次週金曜日にリリースを実施する
- 重要なバグは今週中に修正する

## アクションアイテム
- 山田さん: リリースノートを作成する（期限: 2025-02-05）
- 佐藤さん: バグ#123の修正を完了する
- テストチーム: 回帰テストを実施する（期限: 2025-02-03）
- 資料作成を行う

## 次回の議題
- リリース後の振り返り
"""
    
    # タスク抽出リクエストを作成
    request = TaskExtractRequest(
        job_id="test-job-001",
        summary=test_summary,
        meeting_date=date(2025, 1, 27)
    )
    
    print("=" * 60)
    print("タスク抽出テスト開始")
    print("=" * 60)
    print(f"\nJob ID: {request.job_id}")
    print(f"会議日: {request.meeting_date}")
    print(f"\n議事録要約:\n{test_summary[:200]}...\n")
    
    try:
        # タスク抽出を実行
        service = get_task_service()
        response = await service.extract_tasks(request)
        
        print(f"✓ タスク抽出成功: {len(response.tasks)}件のタスクを抽出")
        print("=" * 60)
        
        # 抽出されたタスクを表示
        for i, task in enumerate(response.tasks, 1):
            print(f"\nタスク {i}:")
            print(f"  タイトル: {task.title}")
            print(f"  説明: {task.description or '(なし)'}")
            print(f"  担当者: {task.assignee}")
            print(f"  期限: {task.due_date}")
            print(f"  抽象的: {'はい' if task.is_abstract else 'いいえ'}")
        
        print("\n" + "=" * 60)
        
        # デフォルト値の検証
        print("\nデフォルト値の検証:")
        
        # 担当者が「未割り当て」になっているタスクを確認
        unassigned_tasks = [t for t in response.tasks if t.assignee == "未割り当て"]
        if unassigned_tasks:
            print(f"✓ 担当者未指定のタスクに「未割り当て」が設定されています ({len(unassigned_tasks)}件)")
        
        # 期限が会議日+7日になっているタスクを確認
        default_due_date = date(2025, 2, 3)  # 2025-01-27 + 7日
        default_due_tasks = [t for t in response.tasks if t.due_date == default_due_date]
        if default_due_tasks:
            print(f"✓ 期限未指定のタスクに会議日+7日が設定されています ({len(default_due_tasks)}件)")
        
        # 明示的な期限が保持されているか確認
        explicit_due_tasks = [t for t in response.tasks if t.due_date != default_due_date]
        if explicit_due_tasks:
            print(f"✓ 明示的な期限が正しく設定されています ({len(explicit_due_tasks)}件)")
        
        print("\n" + "=" * 60)
        print("テスト完了")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_task_extraction())
