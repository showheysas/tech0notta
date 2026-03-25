"""
app/database.py の C0/C1 カバレッジテスト

C0 (命令網羅): 15 テストケース
C1 (分岐網羅): 2 追加テストケース
"""
import pytest
from sqlalchemy import create_engine, inspect, text, Column, String, Integer, DateTime, Text, Boolean
from sqlalchemy.orm import sessionmaker

from app.database import Base


# ============================================================
# get_db テスト
# ============================================================

class TestGetDb:
    """C0: 1件"""

    def test_yields_session(self):
        """C0: セッション yield → close"""
        from app.database import get_db
        gen = get_db()
        session = next(gen)
        assert session is not None
        try:
            gen.send(None)
        except StopIteration:
            pass


# ============================================================
# _ensure_jobs_columns テスト
# ============================================================

class TestEnsureJobsColumns:
    """C0: 5件"""

    def _create_jobs_table(self, engine, extra_columns=None):
        """ヘルパー: 最小限の jobs テーブルを作成"""
        cols = "id INTEGER PRIMARY KEY, filename VARCHAR(255)"
        if extra_columns:
            cols += ", " + extra_columns
        with engine.begin() as conn:
            conn.execute(text(f"CREATE TABLE jobs ({cols})"))

    def test_no_table(self, test_engine, monkeypatch):
        """C0: jobs テーブルなし → 早期return"""
        # test_engine は Base.metadata で users テーブルなどを作るが jobs は手動管理
        # jobs テーブルがない状態でテスト
        engine2 = create_engine("sqlite:///:memory:")
        monkeypatch.setattr("app.database.engine", engine2)
        from app.database import _ensure_jobs_columns
        _ensure_jobs_columns()  # エラーなく完了

    def test_add_transcription_job_id(self, monkeypatch):
        """C0: transcription_job_id カラム追加"""
        engine = create_engine("sqlite:///:memory:")
        self._create_jobs_table(engine)
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_jobs_columns
        _ensure_jobs_columns()
        columns = {col["name"] for col in inspect(engine).get_columns("jobs")}
        assert "transcription_job_id" in columns
        assert "duration" in columns
        assert "last_viewed_at" in columns

    def test_all_columns_present(self, monkeypatch):
        """C0: 全カラム存在 → 何もしない"""
        engine = create_engine("sqlite:///:memory:")
        self._create_jobs_table(
            engine,
            "transcription_job_id VARCHAR(128), duration INTEGER, last_viewed_at DATETIME"
        )
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_jobs_columns
        _ensure_jobs_columns()  # エラーなく完了
        columns = {col["name"] for col in inspect(engine).get_columns("jobs")}
        assert "transcription_job_id" in columns

    def test_partial_columns(self, monkeypatch):
        """C1: 一部カラムのみ存在"""
        engine = create_engine("sqlite:///:memory:")
        self._create_jobs_table(engine, "transcription_job_id VARCHAR(128)")
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_jobs_columns
        _ensure_jobs_columns()
        columns = {col["name"] for col in inspect(engine).get_columns("jobs")}
        assert "duration" in columns
        assert "last_viewed_at" in columns

    def test_duration_only_missing(self, monkeypatch):
        """C1: duration のみ欠落"""
        engine = create_engine("sqlite:///:memory:")
        self._create_jobs_table(engine, "transcription_job_id VARCHAR(128), last_viewed_at DATETIME")
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_jobs_columns
        _ensure_jobs_columns()
        columns = {col["name"] for col in inspect(engine).get_columns("jobs")}
        assert "duration" in columns


# ============================================================
# _ensure_metadata_columns テスト
# ============================================================

class TestEnsureMetadataColumns:
    """C0: 5件, C1: 1件"""

    def _create_jobs_table(self, engine, extra_columns=None):
        cols = "id INTEGER PRIMARY KEY"
        if extra_columns:
            cols += ", " + extra_columns
        with engine.begin() as conn:
            conn.execute(text(f"CREATE TABLE jobs ({cols})"))

    def test_no_table(self, monkeypatch):
        """C0: テーブルなし → 早期return"""
        engine = create_engine("sqlite:///:memory:")
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_metadata_columns
        _ensure_metadata_columns()

    def test_rename_meeting_metadata_sqlite(self, monkeypatch):
        """C0: meeting_metadata→job_metadata リネーム (SQLite)"""
        engine = create_engine("sqlite:///:memory:")
        self._create_jobs_table(engine, "meeting_metadata TEXT")
        monkeypatch.setattr("app.database.engine", engine)
        monkeypatch.setattr("app.database.settings.DATABASE_URL", "sqlite:///test.db")
        from app.database import _ensure_metadata_columns
        _ensure_metadata_columns()
        columns = {col["name"] for col in inspect(engine).get_columns("jobs")}
        assert "job_metadata" in columns

    def test_new_job_metadata(self, monkeypatch):
        """C0: 新規 job_metadata 追加（meeting_metadata も job_metadata もない）"""
        engine = create_engine("sqlite:///:memory:")
        self._create_jobs_table(engine)
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_metadata_columns
        _ensure_metadata_columns()
        columns = {col["name"] for col in inspect(engine).get_columns("jobs")}
        assert "job_metadata" in columns
        assert "extracted_tasks" in columns
        assert "meeting_date" in columns

    def test_extracted_tasks_exists(self, monkeypatch):
        """C1: extracted_tasks が既に存在 → スキップ"""
        engine = create_engine("sqlite:///:memory:")
        self._create_jobs_table(engine, "job_metadata TEXT, extracted_tasks TEXT")
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_metadata_columns
        _ensure_metadata_columns()  # meeting_date のみ追加
        columns = {col["name"] for col in inspect(engine).get_columns("jobs")}
        assert "meeting_date" in columns

    def test_all_metadata_columns_present(self, monkeypatch):
        """C0: 全メタデータカラム存在 → 何もしない"""
        engine = create_engine("sqlite:///:memory:")
        self._create_jobs_table(engine, "job_metadata TEXT, extracted_tasks TEXT, meeting_date DATE")
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_metadata_columns
        _ensure_metadata_columns()


# ============================================================
# _ensure_users_columns テスト
# ============================================================

class TestEnsureUsersColumns:
    """C0: 3件"""

    def test_no_table(self, monkeypatch):
        """C0: テーブルなし → 早期return"""
        engine = create_engine("sqlite:///:memory:")
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_users_columns
        _ensure_users_columns()

    def test_add_columns(self, monkeypatch):
        """C0: email, notion_user_page_id カラム追加"""
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (azure_user_id VARCHAR(36) PRIMARY KEY, is_admin BOOLEAN)"))
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_users_columns
        _ensure_users_columns()
        columns = {col["name"] for col in inspect(engine).get_columns("users")}
        assert "email" in columns
        assert "notion_user_page_id" in columns

    def test_columns_already_present(self, monkeypatch):
        """C0: カラム既存 → 何もしない"""
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE users (azure_user_id VARCHAR(36) PRIMARY KEY, "
                "is_admin BOOLEAN, email VARCHAR(255), notion_user_page_id VARCHAR(36))"
            ))
        monkeypatch.setattr("app.database.engine", engine)
        from app.database import _ensure_users_columns
        _ensure_users_columns()


# ============================================================
# _ensure_chat_tables テスト
# ============================================================

class TestEnsureChatTables:
    """C0: 2件"""

    def test_creates_if_missing(self, monkeypatch, test_engine):
        """C0: テーブルなし → 作成"""
        monkeypatch.setattr("app.database.engine", test_engine)
        from app.database import _ensure_chat_tables
        _ensure_chat_tables()

    def test_tables_already_exist(self, monkeypatch, test_engine):
        """C0: テーブル既存 → 何もしない"""
        monkeypatch.setattr("app.database.engine", test_engine)
        Base.metadata.create_all(bind=test_engine)
        from app.database import _ensure_chat_tables
        _ensure_chat_tables()


# ============================================================
# init_db テスト
# ============================================================

class TestInitDb:
    """C0: 1件"""

    def test_creates_tables(self, monkeypatch, test_engine):
        """C0: テーブル作成確認"""
        monkeypatch.setattr("app.database.engine", test_engine)
        from app.database import init_db
        init_db()
        table_names = inspect(test_engine).get_table_names()
        assert "users" in table_names


# ============================================================
# モジュールレベル分岐テスト
# ============================================================

class TestModuleLevelBranching:
    """C1: 2件 — SQLite vs PostgreSQL の接続設定分岐"""

    def test_sqlite_connect_args(self):
        """C1: SQLite → check_same_thread=False"""
        # database.py のモジュールレベルコードは既にSQLiteで実行済み
        from app.database import connect_args
        assert connect_args == {"check_same_thread": False}

    def test_engine_kwargs_has_pool_pre_ping(self):
        """C1: engine_kwargs に pool_pre_ping が含まれる"""
        from app.database import engine_kwargs
        assert engine_kwargs["pool_pre_ping"] is True
