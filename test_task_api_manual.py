"""
タスクAPI手動テストスクリプト

このスクリプトは、タスクCRUD APIの動作を手動で確認するためのものです。
Notion APIが設定されていない場合は、エラーメッセージが表示されます。
"""
import httpx
import asyncio
from datetime import date, timedelta

BASE_URL = "http://localhost:8000"


async def test_task_endpoints():
    """タスクエンドポイントをテストする"""
    
    async with httpx.AsyncClient() as client:
        print("=" * 60)
        print("タスクAPI手動テスト")
        print("=" * 60)
        
        # 1. タスク一覧取得（フィルターなし）
        print("\n1. タスク一覧取得（フィルターなし）")
        print("-" * 60)
        try:
            response = await client.get(f"{BASE_URL}/api/tasks")
            print(f"ステータスコード: {response.status_code}")
            if response.status_code == 200:
                tasks = response.json()
                print(f"取得したタスク数: {len(tasks)}")
                if tasks:
                    print(f"最初のタスク: {tasks[0].get('title', 'N/A')}")
            else:
                print(f"エラー: {response.text}")
        except Exception as e:
            print(f"例外: {e}")
        
        # 2. タスク一覧取得（ステータスフィルター）
        print("\n2. タスク一覧取得（ステータス=未着手）")
        print("-" * 60)
        try:
            response = await client.get(
                f"{BASE_URL}/api/tasks",
                params={"status": "未着手"}
            )
            print(f"ステータスコード: {response.status_code}")
            if response.status_code == 200:
                tasks = response.json()
                print(f"取得したタスク数: {len(tasks)}")
            else:
                print(f"エラー: {response.text}")
        except Exception as e:
            print(f"例外: {e}")
        
        # 3. タスク一覧取得（優先度フィルター）
        print("\n3. タスク一覧取得（優先度=高）")
        print("-" * 60)
        try:
            response = await client.get(
                f"{BASE_URL}/api/tasks",
                params={"priority": "高"}
            )
            print(f"ステータスコード: {response.status_code}")
            if response.status_code == 200:
                tasks = response.json()
                print(f"取得したタスク数: {len(tasks)}")
            else:
                print(f"エラー: {response.text}")
        except Exception as e:
            print(f"例外: {e}")
        
        # 4. タスク一覧取得（期限範囲フィルター）
        print("\n4. タスク一覧取得（期限範囲フィルター）")
        print("-" * 60)
        try:
            today = date.today()
            next_week = today + timedelta(days=7)
            response = await client.get(
                f"{BASE_URL}/api/tasks",
                params={
                    "due_date_from": today.isoformat(),
                    "due_date_to": next_week.isoformat()
                }
            )
            print(f"ステータスコード: {response.status_code}")
            if response.status_code == 200:
                tasks = response.json()
                print(f"取得したタスク数: {len(tasks)}")
            else:
                print(f"エラー: {response.text}")
        except Exception as e:
            print(f"例外: {e}")
        
        # 5. タスク一覧取得（ソート：期限昇順）
        print("\n5. タスク一覧取得（ソート：期限昇順）")
        print("-" * 60)
        try:
            response = await client.get(
                f"{BASE_URL}/api/tasks",
                params={"sort_by": "due_date", "sort_order": "asc"}
            )
            print(f"ステータスコード: {response.status_code}")
            if response.status_code == 200:
                tasks = response.json()
                print(f"取得したタスク数: {len(tasks)}")
                if len(tasks) >= 2:
                    print(f"最初のタスク期限: {tasks[0].get('due_date', 'N/A')}")
                    print(f"2番目のタスク期限: {tasks[1].get('due_date', 'N/A')}")
            else:
                print(f"エラー: {response.text}")
        except Exception as e:
            print(f"例外: {e}")
        
        # 6. タスク詳細取得（存在しないID）
        print("\n6. タスク詳細取得（存在しないID）")
        print("-" * 60)
        try:
            response = await client.get(f"{BASE_URL}/api/tasks/non-existent-id")
            print(f"ステータスコード: {response.status_code}")
            print(f"レスポンス: {response.text}")
        except Exception as e:
            print(f"例外: {e}")
        
        # 7. タスク更新（存在しないID）
        print("\n7. タスク更新（存在しないID）")
        print("-" * 60)
        try:
            response = await client.put(
                f"{BASE_URL}/api/tasks/non-existent-id",
                json={
                    "title": "更新されたタスク",
                    "status": "進行中"
                }
            )
            print(f"ステータスコード: {response.status_code}")
            print(f"レスポンス: {response.text}")
        except Exception as e:
            print(f"例外: {e}")
        
        # 8. タスク更新（空のタイトル）
        print("\n8. タスク更新（空のタイトル - バリデーションエラー）")
        print("-" * 60)
        try:
            response = await client.put(
                f"{BASE_URL}/api/tasks/test-id",
                json={
                    "title": "",
                    "status": "進行中"
                }
            )
            print(f"ステータスコード: {response.status_code}")
            print(f"レスポンス: {response.text}")
        except Exception as e:
            print(f"例外: {e}")
        
        # 9. タスク削除（存在しないID）
        print("\n9. タスク削除（存在しないID）")
        print("-" * 60)
        try:
            response = await client.delete(f"{BASE_URL}/api/tasks/non-existent-id")
            print(f"ステータスコード: {response.status_code}")
            print(f"レスポンス: {response.text}")
        except Exception as e:
            print(f"例外: {e}")
        
        print("\n" + "=" * 60)
        print("テスト完了")
        print("=" * 60)
        print("\n注意:")
        print("- Notion APIが設定されていない場合、500エラーが返されます")
        print("- 実際のタスクデータを取得するには、NOTION_API_KEYとNOTION_TASK_DB_IDを設定してください")


if __name__ == "__main__":
    print("サーバーが http://localhost:8000 で起動していることを確認してください")
    print("起動していない場合は、別のターミナルで以下を実行してください:")
    print("  cd backend_clone")
    print("  python -m uvicorn app.main:app --reload")
    print()
    
    asyncio.run(test_task_endpoints())
