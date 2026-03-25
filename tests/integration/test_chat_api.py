"""
chat.py (router) の C0/C1 カバレッジテスト

C0: session作成, メッセージ送信(非ストリーミング), 履歴取得, セッション一覧
C1: JobNotFound→404, InvalidMessage→400, SessionNotFound→404, ChatError→500
"""
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.chat import ChatSession, ChatMessage
from app.models.job import Job, JobStatus
from app.routers import chat as chat_router
from app.services.chat_service import (
    ChatService,
    SessionNotFoundError,
    JobNotFoundError,
    InvalidMessageError,
    ChatError,
)
from app.schemas.chat import ChatSessionCreate, ChatMessageCreate


def create_job(db, **overrides):
    job = Job(
        job_id=overrides.pop("job_id", "job-chat-api-1"),
        filename=overrides.pop("filename", "meeting.wav"),
        file_size=overrides.pop("file_size", 100),
        status=overrides.pop("status", JobStatus.SUMMARIZED.value),
        summary=overrides.pop("summary", "要約テキスト"),
        created_at=overrides.pop("created_at", datetime(2026, 3, 22, 12, 0, 0)),
    )
    for k, v in overrides.items():
        setattr(job, k, v)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# ============================================================
# create_chat_session
# ============================================================

class TestCreateChatSession:
    @pytest.mark.asyncio
    async def test_success(self, db_session, test_user, monkeypatch):
        """C0: セッション作成成功"""
        create_job(db_session, job_id="job-cs")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: MagicMock(),
        )
        result = await chat_router.create_chat_session(
            request=ChatSessionCreate(job_id="job-cs"),
            current_user=test_user,
            db=db_session,
        )
        assert result.job_id == "job-cs"
        assert result.session_id is not None

    @pytest.mark.asyncio
    async def test_job_not_found(self, db_session, test_user, monkeypatch):
        """C1: Job未発見 → 404"""
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: MagicMock(),
        )
        with pytest.raises(HTTPException) as exc_info:
            await chat_router.create_chat_session(
                request=ChatSessionCreate(job_id="nonexistent"),
                current_user=test_user,
                db=db_session,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_summary(self, db_session, test_user, monkeypatch):
        """C1: summary無し → 400"""
        create_job(db_session, job_id="job-no-sum-api", summary=None)
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: MagicMock(),
        )
        with pytest.raises(HTTPException) as exc_info:
            await chat_router.create_chat_session(
                request=ChatSessionCreate(job_id="job-no-sum-api"),
                current_user=test_user,
                db=db_session,
            )
        assert exc_info.value.status_code == 400


# ============================================================
# send_chat_message (非ストリーミング)
# ============================================================

class TestSendChatMessage:
    @pytest.mark.asyncio
    async def test_non_streaming_success(self, db_session, test_user, monkeypatch):
        """C0: 非ストリーミングメッセージ送信成功"""
        create_job(db_session, job_id="job-send")
        openai_svc = MagicMock()
        openai_svc.chat_rewrite = MagicMock(return_value="AI応答")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: openai_svc,
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-send")
        result = await chat_router.send_chat_message(
            session_id=session.session_id,
            request=ChatMessageCreate(message="テスト", streaming=False),
            current_user=test_user,
            db=db_session,
        )
        assert result.role == "assistant"
        assert result.content == "AI応答"

    @pytest.mark.asyncio
    async def test_session_not_found(self, db_session, test_user, monkeypatch):
        """C1: SessionNotFound → 404"""
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: MagicMock(),
        )
        with pytest.raises(HTTPException) as exc_info:
            await chat_router.send_chat_message(
                session_id="nonexistent-session",
                request=ChatMessageCreate(message="テスト", streaming=False),
                current_user=test_user,
                db=db_session,
            )
        assert exc_info.value.status_code == 404


# ============================================================
# get_chat_history
# ============================================================

class TestGetChatHistory:
    @pytest.mark.asyncio
    async def test_success(self, db_session, test_user, monkeypatch):
        """C0: 履歴取得成功"""
        create_job(db_session, job_id="job-hist-api")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: MagicMock(),
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-hist-api")
        result = await chat_router.get_chat_history(
            session_id=session.session_id,
            current_user=test_user,
            db=db_session,
        )
        assert result.session_id == session.session_id
        assert result.job_id == "job-hist-api"

    @pytest.mark.asyncio
    async def test_session_not_found(self, db_session, test_user, monkeypatch):
        """C1: SessionNotFound → 404"""
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: MagicMock(),
        )
        with pytest.raises(HTTPException) as exc_info:
            await chat_router.get_chat_history(
                session_id="nonexistent",
                current_user=test_user,
                db=db_session,
            )
        assert exc_info.value.status_code == 404


# ============================================================
# list_chat_sessions
# ============================================================

class TestListChatSessions:
    @pytest.mark.asyncio
    async def test_success(self, db_session, test_user, monkeypatch):
        """C0: セッション一覧取得"""
        create_job(db_session, job_id="job-list-api")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: MagicMock(),
        )
        svc = ChatService(db_session)
        svc.create_session("job-list-api")
        result = await chat_router.list_chat_sessions(
            job_id="job-list-api",
            current_user=test_user,
            db=db_session,
        )
        assert len(result.sessions) == 1
        assert result.sessions[0].job_id == "job-list-api"
