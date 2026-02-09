"""
タスク登録APIのテスト

Task 5.5の実装を検証します。
"""
import asyncio
from datetime import date, timedelta
from app.models.task import (
    TaskRegisterRequest,
    TaskCreate,
    SubTaskCreate,
    TaskPriority
)
from app.services.task_service import get_task_service


async def test_task_registration():
    """タスク登録のテスト"""
    print("=" * 60)
    print("タスク登録APIのテスト")
    print("=" * 60)
    
    # テストデータを作成
    today = date.today()
    due_date = today + timedelta(days=7)
    
    # サブタスク付きのタスクを作成
    task_with_subtasks = TaskCreate(
        title="プロジェクト計画書を作成",
        description="新規プロジェクトの計画書を作成する",
        assignee="山田太郎",
        due_date=due_date,
        priority=TaskPriority.HIGH,
        subtasks=[
            SubTaskCreate(
                title="要件定義を行う",
                description="ステークホルダーと要件を確認",
                order=1
            ),
            SubTaskCreate(
                title="スケジュールを作成する",
                description="マイルストーンとタスクを定義",
                order=2
            ),
            SubTaskCreate(
                title="リソース計画を立てる",
                description="必要な人員と予算を見積もる",
                order=3
            )
        ]
    )
    
    # サブタスクなしのシンプルなタスク
    simple_task = TaskCreate(
        title="議事録を共有する",
        description="チームメンバーに議事録を共有",
        assignee="未割り当て",
        due_date=today + timedelta(days=3),
        priority=TaskPriority.MEDIUM
    )
    
    # タスク登録リクエストを作成
    request = TaskRegisterRequest(
        job_id="test-job-123",
        project_id="test-project-456",
        tasks=[task_with_subtasks, simple_task]
    )
    
    print(f"\n登録するタスク数: {len(request.tasks)}")
    print(f"- タスク1: {task_with_subtasks.title} (サブタスク: {len(task_with_subtasks.subtasks)}個)")
    print(f"- タスク2: {simple_task.title} (サブタスクなし)")
    
    # タスクサービスを取得
    service = get_task_service()
    
    try:
        # タスクを登録
        print("\nタスクを登録中...")
        response = await service.register_tasks(request)
        
        print("\n✅ タスク登録成功!")
        print(f"登録されたタスク/サブタスク数: {response.registered_count}")
        print(f"タスクID: {response.task_ids}")
        
        # 期待される登録数を検証
        # 親タスク2個 + サブタスク3個 = 5個
        expected_count = 5
        if response.registered_count == expected_count:
            print(f"\n✅ 期待通りの数のタスクが登録されました ({expected_count}個)")
        else:
            print(f"\n⚠️ 登録数が期待と異なります (期待: {expected_count}, 実際: {response.registered_count})")
        
    except NotImplementedError as e:
        print(f"\n⚠️ 実装が未完了です: {e}")
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()


async def test_task_registration_validation():
    """タスク登録のバリデーションテスト"""
    print("\n" + "=" * 60)
    print("タスク登録バリデーションのテスト")
    print("=" * 60)
    
    # 必須フィールドが揃っているタスク
    valid_task = TaskCreate(
        title="有効なタスク",
        due_date=date.today() + timedelta(days=7),
        priority=TaskPriority.MEDIUM
    )
    
    request = TaskRegisterRequest(
        job_id="test-job-validation",
        project_id="test-project-validation",
        tasks=[valid_task]
    )
    
    service = get_task_service()
    
    try:
        print("\n有効なタスクを登録中...")
        response = await service.register_tasks(request)
        print(f"✅ バリデーション成功: {response.registered_count}個のタスクが登録されました")
    except Exception as e:
        print(f"❌ バリデーションエラー: {e}")


async def main():
    """メインテスト実行"""
    print("\n🚀 タスク登録API (Task 5.5) のテスト開始\n")
    
    # テスト1: 基本的なタスク登録
    await test_task_registration()
    
    # テスト2: バリデーション
    await test_task_registration_validation()
    
    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)
    print("\n注意: Notion APIキーとTask DB IDが設定されていない場合、")
    print("実際のNotion登録は行われません。")
    print("環境変数 NOTION_API_KEY と NOTION_TASK_DB_ID を設定してください。")


if __name__ == "__main__":
    asyncio.run(main())
