"""
テストデータ作成スクリプト
チャットリライト機能のテスト用に疑似データを1件作成します。
"""
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app.models.job import Job, JobStatus
from app.models.chat import ChatSession, ChatMessage  # ChatSessionをインポート

# テーブルを作成
Base.metadata.create_all(bind=engine)

def create_test_job():
    """テスト用の議事録データを作成"""
    db = SessionLocal()
    try:
        # 既存のテストデータを確認（毎回新しいデータを作成）
        # existing = db.query(Job).filter(Job.filename == "test_meeting_audio.mp3").first()
        # if existing:
        #     print(f"テストデータは既に存在します: job_id={existing.job_id}")
        #     return existing.job_id
        
        # 新しいテストデータを作成
        job_id = str(uuid.uuid4())
        current_time = datetime.now()
        test_job = Job(
            job_id=job_id,
            filename=f"test_meeting_{current_time.strftime('%Y%m%d_%H%M%S')}.mp3",
            file_size=5242880,  # 5MB
            blob_name=f"audio/{job_id}/test_meeting_audio.mp3",
            blob_url=f"https://st002tech0nottadevje.blob.core.windows.net/uploaded-audio/audio/{job_id}/test_meeting_audio.mp3",
            status=JobStatus.SUMMARIZED.value,  # 要約済み（Notion同期前）の状態
            transcription="""
# 会議の文字起こし

参加者: 田中、佐藤、鈴木

田中: 皆さん、本日はお集まりいただきありがとうございます。今日は新しいプロジェクトについて話し合いたいと思います。

佐藤: はい、よろしくお願いします。具体的にはどのようなプロジェクトでしょうか？

田中: 顧客管理システムの刷新プロジェクトです。現在のシステムは5年前に導入したもので、機能面でも技術面でも限界が来ています。

鈴木: なるほど。具体的にはどのような課題がありますか？

田中: 主な課題は3つあります。1つ目は処理速度の低下、2つ目はモバイル対応の不足、3つ目はデータ分析機能の欠如です。

佐藤: それは確かに重要な課題ですね。予算はどのくらいを想定していますか？

田中: 概算で3000万円程度を考えています。期間は1年を予定しています。

鈴木: 分かりました。次回までに詳細な提案書を作成します。

田中: よろしくお願いします。それでは本日はこれで終了します。
            """.strip(),
            transcription_job_id=f"transcription_{job_id}",
            summary="""
# 会議サマリー

## 会議情報
- **日時**: 2025年2月4日
- **参加者**: 田中、佐藤、鈴木
- **議題**: 新製品開発プロジェクトのキックオフ

## 主な議論内容

### 1. プロジェクト概要
- 新しいモバイルアプリの開発プロジェクトを開始
- ターゲット: 20-30代のビジネスパーソン

### 2. 開発スケジュール
1. **要件定義**: 2週間（2月5日〜2月18日）
2. **設計フェーズ**: 3週間（2月19日〜3月11日）
3. **開発フェーズ**: 8週間（3月12日〜5月6日）
4. **テストフェーズ**: 2週間（5月7日〜5月20日）
5. **リリース**: 5月末予定

### 3. 予算と体制
- **予算**: 5000万円
- **開発チーム**: 5名（フロントエンド2名、バックエンド2名、デザイナー1名）
- **プロジェクトマネージャー**: 田中

## アクションアイテム
- [ ] 田中: 要件定義書のドラフトを作成（期限: 2月7日）
- [ ] 佐藤: 競合分析レポートを作成（期限: 2月10日）
- [ ] 鈴木: 技術スタックの選定と提案（期限: 2月12日）

## 次回会議
- 日程: 2月15日 14:00
- 場所: 会議室A
- 議題: 要件定義レビュー
            """.strip(),
            notion_page_id=None,  # Notion未同期
            notion_page_url=None,  # Notion未同期
            duration=1800,  # 30分
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_viewed_at=datetime.now()
        )
        
        db.add(test_job)
        db.commit()
        db.refresh(test_job)
        
        print(f"✅ テストデータを作成しました！")
        print(f"   Job ID: {test_job.job_id}")
        print(f"   ファイル名: {test_job.filename}")
        print(f"   ステータス: {test_job.status}")
        print(f"\n📝 ブラウザで確認: http://localhost:3000/review/{test_job.job_id}")
        
        return test_job.job_id
        
    except Exception as e:
        db.rollback()
        print(f"❌ エラーが発生しました: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    create_test_job()
