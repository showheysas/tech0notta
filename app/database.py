from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

connect_args = {}
engine_kwargs = {"pool_pre_ping": True}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # 新規テーブルモデルをインポートして登録
    import app.models.notification_db  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _ensure_jobs_columns()
    _ensure_chat_tables()
    _ensure_metadata_columns()  # MVP新機能用カラム追加


def _ensure_jobs_columns():
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("jobs")}
    if "transcription_job_id" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN transcription_job_id VARCHAR(128)"))
    if "duration" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN duration INTEGER"))
    if "last_viewed_at" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN last_viewed_at DATETIME"))


def _ensure_metadata_columns():
    """MVP新機能用のメタデータカラムを追加"""
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("jobs")}
    
    # job_metadata カラム（JSON形式でメタデータを保存）
    # 旧カラム名 meeting_metadata から job_metadata にリネーム
    if "meeting_metadata" in columns and "job_metadata" not in columns:
        with engine.begin() as conn:
            # SQLiteの場合はカラムリネームが制限されているため、データをコピーして新カラムを作成
            if settings.DATABASE_URL.startswith("sqlite"):
                conn.execute(text("ALTER TABLE jobs ADD COLUMN job_metadata TEXT"))
                conn.execute(text("UPDATE jobs SET job_metadata = meeting_metadata"))
                # SQLiteではALTER TABLE DROP COLUMNがサポートされていないため、旧カラムは残す
            else:
                conn.execute(text("ALTER TABLE jobs RENAME COLUMN meeting_metadata TO job_metadata"))
    elif "job_metadata" not in columns and "meeting_metadata" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN job_metadata TEXT"))
    
    # extracted_tasks カラム（JSON形式で抽出タスクを保存）
    if "extracted_tasks" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN extracted_tasks TEXT"))
    
    # meeting_date カラム（会議日）
    if "meeting_date" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN meeting_date DATE"))


def _ensure_chat_tables():
    """チャット関連のテーブルが存在することを確認"""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    # chat_sessionsテーブルが存在しない場合は作成
    if "chat_sessions" not in table_names or "chat_messages" not in table_names:
        Base.metadata.create_all(bind=engine)
