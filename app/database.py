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


def _ensure_chat_tables():
    """チャット関連のテーブルが存在することを確認"""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    # chat_sessionsテーブルが存在しない場合は作成
    if "chat_sessions" not in table_names or "chat_messages" not in table_names:
        Base.metadata.create_all(bind=engine)
