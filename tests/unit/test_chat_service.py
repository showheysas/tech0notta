"""
chat_service.py の C0/C1 カバレッジテスト

C0: create_session, get_session, send_message, get_messages, build_context, list_sessions の正常系
C1: job未発見, summary未生成, session未発見, streaming分岐, 過去メッセージ有無, job_idフィルタ
"""
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.chat import ChatSession, ChatMessage
from app.models.job import Job, JobStatus
from app.services.chat_service import (
    ChatService,
    ChatError,
    SessionNotFoundError,
    JobNotFoundError,
    InvalidMessageError,
)


def build_openai_service(response_content="AI応答"):
    svc = MagicMock()
    svc.chat_rewrite = MagicMock(return_value=response_content)
    return svc


def create_job(db, **overrides):
    job = Job(
        job_id=overrides.pop("job_id", "job-chat-1"),
        filename=overrides.pop("filename", "meeting.wav"),
        file_size=overrides.pop("file_size", 100),
        status=overrides.pop("status", JobStatus.SUMMARIZED.value),
        summary=overrides.pop("summary", "要約テキスト"),
    )
    for k, v in overrides.items():
        setattr(job, k, v)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# ============================================================
# create_session
# ============================================================

class TestCreateSession:
    def test_success(self, db_session, monkeypatch):
        """C0: 正常にセッション作成"""
        create_job(db_session, job_id="job-1", summary="要約")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-1")
        assert session.job_id == "job-1"
        assert session.session_id is not None

    def test_job_not_found(self, db_session, monkeypatch):
        """C1: Job未発見 → JobNotFoundError"""
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        with pytest.raises(JobNotFoundError):
            svc.create_session("nonexistent-job")

    def test_no_summary(self, db_session, monkeypatch):
        """C1: summary未生成 → InvalidMessageError"""
        create_job(db_session, job_id="job-no-sum", summary=None)
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        with pytest.raises(InvalidMessageError):
            svc.create_session("job-no-sum")


# ============================================================
# get_session
# ============================================================

class TestGetSession:
    def test_success(self, db_session, monkeypatch):
        """C0: セッション取得成功"""
        create_job(db_session, job_id="job-gs")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        created = svc.create_session("job-gs")
        result = svc.get_session(created.session_id)
        assert result.session_id == created.session_id

    def test_not_found(self, db_session, monkeypatch):
        """C1: セッション未発見 → SessionNotFoundError"""
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        with pytest.raises(SessionNotFoundError):
            svc.get_session("nonexistent-session")


# ============================================================
# send_message (非ストリーミング)
# ============================================================

class TestSendMessage:
    def test_non_streaming_success(self, db_session, monkeypatch):
        """C0: 非ストリーミングで AI 応答取得"""
        create_job(db_session, job_id="job-sm")
        openai_svc = build_openai_service("修正後の議事録")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: openai_svc,
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-sm")
        result = svc.send_message(session.session_id, "要約を短くして", streaming=False)
        assert result == "修正後の議事録"
        # ユーザーメッセージとアシスタントメッセージが保存されること
        messages = db_session.query(ChatMessage).filter(
            ChatMessage.session_id == session.session_id
        ).all()
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    def test_streaming_returns_generator(self, db_session, monkeypatch):
        """C1: ストリーミング → ジェネレータ返却"""
        create_job(db_session, job_id="job-stream")
        openai_svc = build_openai_service()
        openai_svc.chat_rewrite = MagicMock(return_value=iter(["chunk1", "chunk2"]))
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: openai_svc,
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-stream")
        gen = svc.send_message(session.session_id, "テスト", streaming=True)
        # ジェネレータを消費
        chunks = list(gen)
        assert chunks == ["chunk1", "chunk2"]

    def test_job_not_found_during_send(self, db_session, monkeypatch):
        """C1: send_message 中に job/summary 未発見"""
        create_job(db_session, job_id="job-del")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-del")
        # summary を削除して「job or summary not found」分岐を通す
        job = db_session.query(Job).filter(Job.job_id == "job-del").first()
        job.summary = None
        db_session.commit()
        with pytest.raises(JobNotFoundError):
            svc.send_message(session.session_id, "テスト")

    def test_generate_response_error(self, db_session, monkeypatch):
        """C1: AI応答生成失敗 → ChatError"""
        create_job(db_session, job_id="job-err")
        openai_svc = build_openai_service()
        openai_svc.chat_rewrite = MagicMock(side_effect=RuntimeError("API failed"))
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: openai_svc,
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-err")
        with pytest.raises(ChatError, match="Failed to generate response"):
            svc.send_message(session.session_id, "テスト", streaming=False)


# ============================================================
# build_context
# ============================================================

class TestBuildContext:
    def test_first_message_includes_summary(self, db_session, monkeypatch):
        """C0: 最初のメッセージ → 元の議事録を含む"""
        create_job(db_session, job_id="job-ctx")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-ctx")
        context = svc.build_context(session.session_id, "元の要約", "修正して")
        assert any("元の要約" in m["content"] for m in context)
        assert context[-1]["content"] == "修正して"

    def test_subsequent_message_includes_history(self, db_session, monkeypatch):
        """C1: 過去メッセージあり → 履歴を含む"""
        create_job(db_session, job_id="job-hist")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-hist")
        # 過去メッセージを手動追加
        msg1 = ChatMessage(
            message_id="msg-1", session_id=session.session_id, role="user", content="以前の質問"
        )
        msg2 = ChatMessage(
            message_id="msg-2", session_id=session.session_id, role="assistant", content="以前の回答"
        )
        db_session.add_all([msg1, msg2])
        db_session.commit()
        context = svc.build_context(session.session_id, "元の要約", "新しい質問")
        roles = [m["role"] for m in context]
        assert "user" in roles
        assert "assistant" in roles
        assert context[-1]["content"] == "新しい質問"


# ============================================================
# get_messages
# ============================================================

class TestGetMessages:
    def test_returns_ordered_messages(self, db_session, monkeypatch):
        """C0: メッセージ取得 (created_at順)"""
        create_job(db_session, job_id="job-gm")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        session = svc.create_session("job-gm")
        msg = ChatMessage(
            message_id="msg-gm-1", session_id=session.session_id, role="user", content="テスト"
        )
        db_session.add(msg)
        db_session.commit()
        messages = svc.get_messages(session.session_id)
        assert len(messages) == 1
        assert messages[0].content == "テスト"


# ============================================================
# list_sessions
# ============================================================

class TestListSessions:
    def test_list_all(self, db_session, monkeypatch):
        """C0: 全セッション一覧"""
        create_job(db_session, job_id="job-ls1")
        create_job(db_session, job_id="job-ls2")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        svc.create_session("job-ls1")
        svc.create_session("job-ls2")
        sessions = svc.list_sessions()
        assert len(sessions) == 2

    def test_filter_by_job_id(self, db_session, monkeypatch):
        """C1: job_idフィルタ"""
        create_job(db_session, job_id="job-f1")
        create_job(db_session, job_id="job-f2")
        monkeypatch.setattr(
            "app.services.chat_service.get_azure_openai_service",
            lambda: build_openai_service(),
        )
        svc = ChatService(db_session)
        svc.create_session("job-f1")
        svc.create_session("job-f2")
        sessions = svc.list_sessions(job_id="job-f1")
        assert len(sessions) == 1
        assert sessions[0]["job_id"] == "job-f1"
