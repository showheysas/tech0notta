"""
タスク分解機能のテスト

Task 5.3の実装を検証するための簡易テストスクリプト
"""
import asyncio
from datetime import date
from app.models.task import TaskDecomposeRequest
from app.services.task_service import get_task_service


async def test_task_decomposition():
    """タスク分解のテスト"""
    
    # テストケース1: 抽象的なタスク（資料作成）
    test_cases = [
        {
            "task_title": "プロジェクト提案資料を作成する",
            "task_description": "新規プロジェクトの提案資料を作成し、経営陣に提出する",
            "parent_due_date": date(2025, 2, 15)
        },
        {
            "task_title": "システムの調査を実施する",
            "task_description": "競合他社のシステムを調査し、比較レポートを作成する",
            "parent_due_date": date(2025, 2, 20)
        },
        {
            "task_title": "新機能の開発",
            "task_description": None,
            "parent_due_date": date(2025, 3, 1)
        }
    ]
    
    print("=" * 60)
    print("タスク分解テスト開始")
    print("=" * 60)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'=' * 60}")
        print(f"テストケース {i}")
        print("=" * 60)
        print(f"タスク: {test_case['task_title']}")
        print(f"説明: {test_case['task_description'] or '(なし)'}")
        print(f"期限: {test_case['parent_due_date']}")
        print()
        
        try:
            # タスク分解リクエストを作成
            request = TaskDecomposeRequest(
                task_title=test_case["task_title"],
                task_description=test_case["task_description"],
                parent_due_date=test_case["parent_due_date"]
            )
            
            # タスク分解を実行
            service = get_task_service()
            response = await service.decompose_task(request)
            
            print(f"✓ タスク分解成功: {len(response.subtasks)}個のサブタスクを生成")
            print(f"親タスク: {response.parent_task}")
            print()
            
            # サブタスクを表示
            for subtask in response.subtasks:
                print(f"  [{subtask.order}] {subtask.title}")
                if subtask.description:
                    print(f"      説明: {subtask.description}")
            
            # 検証
            print("\n検証結果:")
            
            # サブタスク数の検証（3-5個）
            if 3 <= len(response.subtasks) <= 5:
                print(f"  ✓ サブタスク数が適切です ({len(response.subtasks)}個)")
            else:
                print(f"  ✗ サブタスク数が範囲外です ({len(response.subtasks)}個、期待: 3-5個)")
            
            # 順序の検証（1から始まる連番）
            orders = [st.order for st in response.subtasks]
            expected_orders = list(range(1, len(response.subtasks) + 1))
            if orders == expected_orders:
                print(f"  ✓ サブタスクの順序が正しいです (1-{len(response.subtasks)})")
            else:
                print(f"  ✗ サブタスクの順序が不正です (実際: {orders}, 期待: {expected_orders})")
            
            # タイトルの存在確認
            all_have_titles = all(st.title and st.title.strip() for st in response.subtasks)
            if all_have_titles:
                print("  ✓ すべてのサブタスクにタイトルがあります")
            else:
                print("  ✗ タイトルが空のサブタスクがあります")
            
        except Exception as e:
            print(f"\n✗ エラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)


async def test_edge_cases():
    """エッジケースのテスト"""
    
    print("\n" + "=" * 60)
    print("エッジケーステスト")
    print("=" * 60)
    
    # エッジケース: 非常に短いタスク名
    print("\nテスト: 短いタスク名")
    try:
        request = TaskDecomposeRequest(
            task_title="調査",
            task_description=None,
            parent_due_date=date(2025, 2, 10)
        )
        service = get_task_service()
        response = await service.decompose_task(request)
        print(f"✓ 成功: {len(response.subtasks)}個のサブタスクを生成")
    except Exception as e:
        print(f"✗ エラー: {e}")
    
    # エッジケース: 非常に長いタスク説明
    print("\nテスト: 長いタスク説明")
    try:
        long_description = "このタスクは非常に複雑で、" * 50
        request = TaskDecomposeRequest(
            task_title="複雑なタスク",
            task_description=long_description,
            parent_due_date=date(2025, 2, 10)
        )
        service = get_task_service()
        response = await service.decompose_task(request)
        print(f"✓ 成功: {len(response.subtasks)}個のサブタスクを生成")
    except Exception as e:
        print(f"✗ エラー: {e}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_task_decomposition())
    asyncio.run(test_edge_cases())
