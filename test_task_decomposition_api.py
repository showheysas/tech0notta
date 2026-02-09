"""
タスク分解API統合テスト

Task 5.3のAPIエンドポイントを検証するための統合テストスクリプト
"""
import asyncio
import sys
from datetime import date
from fastapi.testclient import TestClient

# アプリケーションのインポート
from app.main import app

client = TestClient(app)


def test_decompose_task_api():
    """タスク分解APIのテスト"""
    
    print("=" * 60)
    print("タスク分解API統合テスト")
    print("=" * 60)
    
    # テストケース
    test_cases = [
        {
            "name": "基本的なタスク分解",
            "payload": {
                "task_title": "プロジェクト提案資料を作成する",
                "task_description": "新規プロジェクトの提案資料を作成し、経営陣に提出する",
                "parent_due_date": "2025-02-15"
            }
        },
        {
            "name": "説明なしのタスク分解",
            "payload": {
                "task_title": "新機能の開発",
                "parent_due_date": "2025-03-01"
            }
        },
        {
            "name": "短いタスク名",
            "payload": {
                "task_title": "調査",
                "parent_due_date": "2025-02-10"
            }
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'=' * 60}")
        print(f"テストケース {i}: {test_case['name']}")
        print("=" * 60)
        print(f"リクエスト: {test_case['payload']}")
        
        try:
            # APIエンドポイントを呼び出し
            response = client.post("/api/tasks/decompose", json=test_case["payload"])
            
            # ステータスコードの確認
            if response.status_code == 200:
                print(f"✓ ステータスコード: {response.status_code} (成功)")
                
                # レスポンスの解析
                data = response.json()
                print(f"\n親タスク: {data['parent_task']}")
                print(f"サブタスク数: {len(data['subtasks'])}")
                
                # サブタスクの表示
                print("\nサブタスク:")
                for subtask in data["subtasks"]:
                    print(f"  [{subtask['order']}] {subtask['title']}")
                    if subtask.get("description"):
                        print(f"      説明: {subtask['description'][:80]}...")
                
                # 検証
                print("\n検証結果:")
                
                # サブタスク数の検証（3-5個）
                subtask_count = len(data["subtasks"])
                if 3 <= subtask_count <= 5:
                    print(f"  ✓ サブタスク数が適切です ({subtask_count}個)")
                else:
                    print(f"  ✗ サブタスク数が範囲外です ({subtask_count}個、期待: 3-5個)")
                
                # 順序の検証
                orders = [st["order"] for st in data["subtasks"]]
                expected_orders = list(range(1, subtask_count + 1))
                if orders == expected_orders:
                    print(f"  ✓ サブタスクの順序が正しいです (1-{subtask_count})")
                else:
                    print(f"  ✗ サブタスクの順序が不正です (実際: {orders}, 期待: {expected_orders})")
                
                # タイトルの存在確認
                all_have_titles = all(st["title"] and st["title"].strip() for st in data["subtasks"])
                if all_have_titles:
                    print("  ✓ すべてのサブタスクにタイトルがあります")
                else:
                    print("  ✗ タイトルが空のサブタスクがあります")
                
                # 親タスク名の一致確認
                if data["parent_task"] == test_case["payload"]["task_title"]:
                    print("  ✓ 親タスク名が一致しています")
                else:
                    print(f"  ✗ 親タスク名が不一致です (期待: {test_case['payload']['task_title']}, 実際: {data['parent_task']})")
                
            else:
                print(f"✗ ステータスコード: {response.status_code} (失敗)")
                print(f"エラー詳細: {response.json()}")
                
        except Exception as e:
            print(f"\n✗ エラーが発生しました: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("テスト完了")
    print("=" * 60)


def test_error_cases():
    """エラーケースのテスト"""
    
    print("\n" + "=" * 60)
    print("エラーケーステスト")
    print("=" * 60)
    
    # エラーケース: 必須フィールドの欠落
    print("\nテスト: 必須フィールド欠落（task_title）")
    try:
        response = client.post("/api/tasks/decompose", json={
            "parent_due_date": "2025-02-15"
        })
        if response.status_code == 422:
            print(f"✓ 期待通りのエラー: {response.status_code} (バリデーションエラー)")
        else:
            print(f"✗ 予期しないステータスコード: {response.status_code}")
    except Exception as e:
        print(f"✗ エラー: {e}")
    
    # エラーケース: 不正な日付形式
    print("\nテスト: 不正な日付形式")
    try:
        response = client.post("/api/tasks/decompose", json={
            "task_title": "テストタスク",
            "parent_due_date": "invalid-date"
        })
        if response.status_code == 422:
            print(f"✓ 期待通りのエラー: {response.status_code} (バリデーションエラー)")
        else:
            print(f"✗ 予期しないステータスコード: {response.status_code}")
    except Exception as e:
        print(f"✗ エラー: {e}")
    
    print("\n" + "=" * 60)


def test_response_schema():
    """レスポンススキーマのテスト"""
    
    print("\n" + "=" * 60)
    print("レスポンススキーマテスト")
    print("=" * 60)
    
    payload = {
        "task_title": "テストタスク",
        "task_description": "テスト用の説明",
        "parent_due_date": "2025-02-15"
    }
    
    print(f"\nリクエスト: {payload}")
    
    try:
        response = client.post("/api/tasks/decompose", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            
            print("\nスキーマ検証:")
            
            # 必須フィールドの確認
            required_fields = ["parent_task", "subtasks"]
            for field in required_fields:
                if field in data:
                    print(f"  ✓ {field} フィールドが存在します")
                else:
                    print(f"  ✗ {field} フィールドが欠落しています")
            
            # サブタスクのスキーマ確認
            if "subtasks" in data and len(data["subtasks"]) > 0:
                subtask = data["subtasks"][0]
                subtask_fields = ["title", "order"]
                for field in subtask_fields:
                    if field in subtask:
                        print(f"  ✓ サブタスクに {field} フィールドが存在します")
                    else:
                        print(f"  ✗ サブタスクに {field} フィールドが欠落しています")
                
                # orderが整数型か確認
                if isinstance(subtask["order"], int):
                    print("  ✓ order フィールドは整数型です")
                else:
                    print(f"  ✗ order フィールドの型が不正です: {type(subtask['order'])}")
            
        else:
            print(f"✗ APIリクエストが失敗しました: {response.status_code}")
            
    except Exception as e:
        print(f"\n✗ エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_decompose_task_api()
    test_error_cases()
    test_response_schema()
    
    print("\n" + "=" * 60)
    print("すべてのテストが完了しました")
    print("=" * 60)
