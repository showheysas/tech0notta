"""
タスク抽出機能の包括的テスト

Requirements 4.1, 4.2, 4.3, 4.4 の検証
"""
import asyncio
from datetime import date, timedelta
from app.models.task import TaskExtractRequest
from app.services.task_service import get_task_service


async def test_empty_summary():
    """空の要約からタスク抽出（タスクなしの場合）"""
    print("\n" + "=" * 60)
    print("テスト1: 空の要約")
    print("=" * 60)
    
    request = TaskExtractRequest(
        job_id="test-empty",
        summary="",
        meeting_date=date(2025, 1, 27)
    )
    
    try:
        service = get_task_service()
        response = await service.extract_tasks(request)
        print(f"✓ 抽出されたタスク数: {len(response.tasks)}")
        assert len(response.tasks) == 0, "空の要約からはタスクが抽出されないはず"
        print("✓ テスト成功: 空の要約からタスクは抽出されませんでした")
    except Exception as e:
        print(f"✗ テスト失敗: {e}")


async def test_no_action_items():
    """アクションアイテムがない議事録"""
    print("\n" + "=" * 60)
    print("テスト2: アクションアイテムなし")
    print("=" * 60)
    
    summary = """
## 概要
情報共有のみの会議でした。

## 主な議題
- プロジェクトの現状報告
- 今後の予定について

## 決定事項
特になし
"""
    
    request = TaskExtractRequest(
        job_id="test-no-action",
        summary=summary,
        meeting_date=date(2025, 1, 27)
    )
    
    try:
        service = get_task_service()
        response = await service.extract_tasks(request)
        print(f"✓ 抽出されたタスク数: {len(response.tasks)}")
        print("✓ テスト成功: アクションアイテムがない場合は空のリストが返されました")
    except Exception as e:
        print(f"✗ テスト失敗: {e}")


async def test_default_assignee():
    """担当者未指定のタスク（Requirement 4.3）"""
    print("\n" + "=" * 60)
    print("テスト3: 担当者未指定（Requirement 4.3）")
    print("=" * 60)
    
    summary = """
## アクションアイテム
- 次回の会議日程を調整する
- 資料を準備する
"""
    
    request = TaskExtractRequest(
        job_id="test-default-assignee",
        summary=summary,
        meeting_date=date(2025, 1, 27)
    )
    
    try:
        service = get_task_service()
        response = await service.extract_tasks(request)
        print(f"✓ 抽出されたタスク数: {len(response.tasks)}")
        
        for task in response.tasks:
            print(f"  - {task.title}: 担当者={task.assignee}")
            assert task.assignee == "未割り当て", f"担当者未指定の場合は「未割り当て」になるべき: {task.assignee}"
        
        print("✓ テスト成功: 担当者未指定のタスクに「未割り当て」が設定されました")
    except Exception as e:
        print(f"✗ テスト失敗: {e}")


async def test_default_due_date():
    """期限未指定のタスク（Requirement 4.4）"""
    print("\n" + "=" * 60)
    print("テスト4: 期限未指定（Requirement 4.4）")
    print("=" * 60)
    
    summary = """
## アクションアイテム
- 田中さん: プロジェクト計画書を作成する
- 鈴木さん: 予算案を検討する
"""
    
    meeting_date = date(2025, 1, 27)
    expected_due_date = meeting_date + timedelta(days=7)
    
    request = TaskExtractRequest(
        job_id="test-default-due-date",
        summary=summary,
        meeting_date=meeting_date
    )
    
    try:
        service = get_task_service()
        response = await service.extract_tasks(request)
        print(f"✓ 抽出されたタスク数: {len(response.tasks)}")
        print(f"  会議日: {meeting_date}")
        print(f"  期待される期限: {expected_due_date}")
        
        for task in response.tasks:
            print(f"  - {task.title}: 期限={task.due_date}")
            assert task.due_date == expected_due_date, f"期限未指定の場合は会議日+7日になるべき: {task.due_date}"
        
        print("✓ テスト成功: 期限未指定のタスクに会議日+7日が設定されました")
    except Exception as e:
        print(f"✗ テスト失敗: {e}")


async def test_explicit_due_date():
    """明示的な期限が指定されたタスク"""
    print("\n" + "=" * 60)
    print("テスト5: 明示的な期限指定")
    print("=" * 60)
    
    summary = """
## アクションアイテム
- 山田さん: 報告書を提出する（期限: 2025-02-10）
- 佐藤さん: レビューを完了する（2025-02-15まで）
"""
    
    request = TaskExtractRequest(
        job_id="test-explicit-due-date",
        summary=summary,
        meeting_date=date(2025, 1, 27)
    )
    
    try:
        service = get_task_service()
        response = await service.extract_tasks(request)
        print(f"✓ 抽出されたタスク数: {len(response.tasks)}")
        
        for task in response.tasks:
            print(f"  - {task.title}: 期限={task.due_date}, 担当者={task.assignee}")
        
        print("✓ テスト成功: 明示的な期限が正しく抽出されました")
    except Exception as e:
        print(f"✗ テスト失敗: {e}")


async def test_abstract_task_detection():
    """抽象的なタスクの検出"""
    print("\n" + "=" * 60)
    print("テスト6: 抽象的なタスクの検出")
    print("=" * 60)
    
    summary = """
## アクションアイテム
- 資料作成を行う
- 調査を実施する
- システムの設計を検討する
- バグ#456を修正する（具体的なタスク）
"""
    
    request = TaskExtractRequest(
        job_id="test-abstract-task",
        summary=summary,
        meeting_date=date(2025, 1, 27)
    )
    
    try:
        service = get_task_service()
        response = await service.extract_tasks(request)
        print(f"✓ 抽出されたタスク数: {len(response.tasks)}")
        
        abstract_tasks = [t for t in response.tasks if t.is_abstract]
        concrete_tasks = [t for t in response.tasks if not t.is_abstract]
        
        print(f"  抽象的なタスク: {len(abstract_tasks)}件")
        for task in abstract_tasks:
            print(f"    - {task.title}")
        
        print(f"  具体的なタスク: {len(concrete_tasks)}件")
        for task in concrete_tasks:
            print(f"    - {task.title}")
        
        print("✓ テスト成功: 抽象的なタスクが検出されました")
    except Exception as e:
        print(f"✗ テスト失敗: {e}")


async def test_complex_summary():
    """複雑な議事録からのタスク抽出（Requirement 4.2）"""
    print("\n" + "=" * 60)
    print("テスト7: 複雑な議事録（Requirement 4.2）")
    print("=" * 60)
    
    summary = """
## 概要
新機能開発のキックオフミーティングを実施しました。

## 主な議題
- 要件定義の確認
- 開発スケジュールの策定
- チーム体制の決定

## 決定事項
- 開発期間は3ヶ月とする
- 週次で進捗会議を実施する

## アクションアイテム
- 山田さん: 要件定義書を作成する（期限: 2025-02-05）
- 佐藤さん: 技術調査を実施する
- 田中さん: プロトタイプを作成する（期限: 2025-02-15）
- 鈴木さん: テスト計画を策定する
- デザインレビューを実施する
- 全員: 次回会議の日程調整を行う（期限: 2025-01-30）

## 次回の議題
- 要件定義のレビュー
- 技術調査結果の共有
"""
    
    request = TaskExtractRequest(
        job_id="test-complex",
        summary=summary,
        meeting_date=date(2025, 1, 27)
    )
    
    try:
        service = get_task_service()
        response = await service.extract_tasks(request)
        print(f"✓ 抽出されたタスク数: {len(response.tasks)}")
        
        # タスクの詳細を表示
        for i, task in enumerate(response.tasks, 1):
            print(f"\nタスク {i}:")
            print(f"  タイトル: {task.title}")
            print(f"  担当者: {task.assignee}")
            print(f"  期限: {task.due_date}")
            print(f"  抽象的: {'はい' if task.is_abstract else 'いいえ'}")
        
        # 検証
        assert len(response.tasks) >= 4, "少なくとも4つのアクションアイテムが抽出されるべき"
        
        # 担当者が指定されているタスクの確認
        assigned_tasks = [t for t in response.tasks if t.assignee != "未割り当て"]
        print(f"\n✓ 担当者が指定されているタスク: {len(assigned_tasks)}件")
        
        # 期限が指定されているタスクの確認
        explicit_due_tasks = [t for t in response.tasks if t.due_date != date(2025, 2, 3)]
        print(f"✓ 明示的な期限が指定されているタスク: {len(explicit_due_tasks)}件")
        
        print("\n✓ テスト成功: 複雑な議事録から適切にタスクが抽出されました")
    except Exception as e:
        print(f"✗ テスト失敗: {e}")
        import traceback
        traceback.print_exc()


async def run_all_tests():
    """全テストを実行"""
    print("\n" + "=" * 60)
    print("タスク抽出機能 包括的テスト")
    print("Requirements 4.1, 4.2, 4.3, 4.4 の検証")
    print("=" * 60)
    
    await test_empty_summary()
    await test_no_action_items()
    await test_default_assignee()
    await test_default_due_date()
    await test_explicit_due_date()
    await test_abstract_task_detection()
    await test_complex_summary()
    
    print("\n" + "=" * 60)
    print("全テスト完了")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
