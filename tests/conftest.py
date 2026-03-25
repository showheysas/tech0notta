"""
テスト共通フィクスチャ
- SQLite in-memory テストDB
- 認証オーバーライド
- 外部サービス mock
"""
import os

# database.py がモジュールレベルで DATABASE_URL を参照するため、import 前に設定
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.user import User
# 全モデルをインポートして SQLAlchemy relationship を解決
import app.models  # noqa: F401
import app.models.chat  # noqa: F401
import app.models.notification_db  # noqa: F401


@pytest.fixture()
def test_engine():
    """テスト用 SQLite in-memory エンジン"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    """テスト用 DB セッション"""
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def test_user(db_session):
    """テスト用ユーザー（管理者）"""
    user = User(
        azure_user_id="test-admin-id",
        email="admin@example.com",
        is_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def test_regular_user(db_session):
    """テスト用ユーザー（一般）"""
    user = User(
        azure_user_id="test-user-id",
        email="user@example.com",
        is_admin=False,
        notion_user_page_id="notion-page-123",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def mock_notion_user_service(mocker):
    """NotionUserService の mock"""
    mock_svc = mocker.MagicMock()
    mock_svc.enabled = True
    mock_svc.resolve_by_email = mocker.AsyncMock(return_value=None)
    mock_svc.get_project_ids_for_user = mocker.AsyncMock(return_value=set())
    mocker.patch("app.auth.get_notion_user_service", return_value=mock_svc)
    return mock_svc
