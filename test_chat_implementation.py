"""
対話型リライト機能の実装テスト

このスクリプトは、チャット機能の基本的な動作を確認します。
"""

import sys
import os

# パスを追加
sys.path.insert(0, os.path.dirname(__file__))

from app.database import init_db, SessionLocal
from app.models.job import Job, JobStatus
from app.models.chat import ChatSession, ChatMessage
from app.services.chat_service import ChatService
import uuid


def test_database_setup():
    """データベースのセットアップをテスト"""
    print("=== データベースセットアップテスト ===")
    try:
        init_db()
        print("✓ データベース初期化成功")
        return True
    except Exception as e:
        print(f"✗ データベース初期化失敗: {e}")
        return False


def test_create_test_job():
    """テスト用のJobを作成"""
    print("\n=== テストJob作成 ===")
    db = SessionLocal()
    try:
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            filename="test_meeting.mp3",
            file_size=1024,
            status=JobStatus.SUMMARIZED.value,
            summary="""## 概要
これはテスト用の議事録です。

## 主な議題
- プロジェクトの進捗確認
- 次のステップの決定

## 決定事項
- 来週までに実装を完了する
- レビューは金曜日に実施

## アクションアイテム
- 田中さん: 設計書の作成
- 佐藤さん: テストケースの準備
"""
        )
        
        db.add(job)
        db.commit()
        db.refresh(job)
        
        print(f"✓ テストJob作成成功: {job_id}")
        return job_id
    except Exception as e:
        print(f"✗ テストJob作成失敗: {e}")
        db.rollback()
        return None
    finally:
        db.close()


def test_create_chat_session(job_id: str):
    """チャットセッションの作成をテスト"""
    print("\n=== チャットセッション作成テスト ===")
    db = SessionLocal()
    try:
        chat_service = ChatService(db)
        session = chat_service.create_session(job_id)
        
        print(f"✓ セッション作成成功: {session.session_id}")
        return session.session_id
    except Exception as e:
        print(f"✗ セッション作成失敗: {e}")
        return None
    finally:
        db.close()


def test_chat_context_building(session_id: str):
    """コンテキスト構築をテスト"""
    print("\n=== コンテキスト構築テスト ===")
    db = SessionLocal()
    try:
        chat_service = ChatService(db)
        session = chat_service.get_session(session_id)
        
        # Jobを取得
        job = db.query(Job).filter(Job.job_id == session.job_id).first()
        
        # コンテキストを構築
        context = chat_service.build_context(
            session_id,
            job.summary,
            "要約を短くしてください"
        )
        
        print(f"✓ コンテキスト構築成功")
        print(f"  メッセージ数: {len(context)}")
        print(f"  システムプロンプト: {context[0]['role'] == 'system'}")
        return True
    except Exception as e:
        print(f"✗ コンテキスト構築失敗: {e}")
        return False
    finally:
        db.close()


def test_list_sessions(job_id: str):
    """セッション一覧取得をテスト"""
    print("\n=== セッション一覧取得テスト ===")
    db = SessionLocal()
    try:
        chat_service = ChatService(db)
        sessions = chat_service.list_sessions(job_id)
        
        print(f"✓ セッション一覧取得成功")
        print(f"  セッション数: {len(sessions)}")
        for session in sessions:
            print(f"  - {session['session_id']}: {session['message_count']}件のメッセージ")
        return True
    except Exception as e:
        print(f"✗ セッション一覧取得失敗: {e}")
        return False
    finally:
        db.close()


def main():
    """メインテスト実行"""
    print("対話型リライト機能 - 実装テスト")
    print("=" * 50)
    
    # 1. データベースセットアップ
    if not test_database_setup():
        print("\n❌ データベースセットアップに失敗しました")
        return
    
    # 2. テストJob作成
    job_id = test_create_test_job()
    if not job_id:
        print("\n❌ テストJobの作成に失敗しました")
        return
    
    # 3. チャットセッション作成
    session_id = test_create_chat_session(job_id)
    if not session_id:
        print("\n❌ チャットセッションの作成に失敗しました")
        return
    
    # 4. コンテキスト構築
    if not test_chat_context_building(session_id):
        print("\n❌ コンテキスト構築に失敗しました")
        return
    
    # 5. セッション一覧取得
    if not test_list_sessions(job_id):
        print("\n❌ セッション一覧取得に失敗しました")
        return
    
    print("\n" + "=" * 50)
    print("✅ すべてのテストが成功しました！")
    print("\n次のステップ:")
    print("1. サーバーを起動: python -m uvicorn app.main:app --reload")
    print("2. APIエンドポイントをテスト:")
    print(f"   - POST /api/chat/sessions (job_id: {job_id})")
    print(f"   - POST /api/chat/sessions/{session_id}/messages")
    print(f"   - GET /api/chat/sessions/{session_id}/messages")


if __name__ == "__main__":
    main()
