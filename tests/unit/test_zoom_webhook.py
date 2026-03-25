import hashlib
import hmac
import json
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routers import zoom_webhook as webhook


class DummyRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


def install_bot_service(monkeypatch, bot_service):
    module = ModuleType("app.services.bot_service")
    module.bot_service = bot_service
    monkeypatch.setitem(sys.modules, "app.services.bot_service", module)


def build_signature(secret: str, timestamp: str, body: bytes) -> str:
    message = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"v0={digest}"


def test_verify_zoom_signature_returns_true_for_valid_signature():
    body = b'{"event":"meeting.started"}'
    timestamp = "1700000000"
    secret = "secret-token"
    signature = build_signature(secret, timestamp, body)

    result = webhook.verify_zoom_signature(body, timestamp, signature, secret)

    assert result is True


def test_create_challenge_response_returns_expected_hash():
    response = webhook.create_challenge_response("plain-token", "secret-token")
    expected_hash = hmac.new(
        b"secret-token",
        b"plain-token",
        hashlib.sha256,
    ).hexdigest()

    assert response.plainToken == "plain-token"
    assert response.encryptedToken == expected_hash


@pytest.mark.asyncio
async def test_zoom_webhook_rejects_invalid_json():
    request = DummyRequest(b"{invalid")

    with pytest.raises(HTTPException) as exc_info:
        await webhook.zoom_webhook(request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid JSON payload"


@pytest.mark.asyncio
async def test_zoom_webhook_rejects_crc_without_plain_token():
    body = json.dumps({"event": "endpoint.url_validation", "payload": {}}).encode("utf-8")
    request = DummyRequest(body)

    with pytest.raises(HTTPException) as exc_info:
        await webhook.zoom_webhook(request)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "plainToken not found"


@pytest.mark.asyncio
async def test_zoom_webhook_returns_crc_response(monkeypatch):
    monkeypatch.setattr(webhook.zoom_config, "webhook_secret_token", "secret-token")
    body = json.dumps(
        {
            "event": "endpoint.url_validation",
            "payload": {"plainToken": "plain-token"},
        }
    ).encode("utf-8")
    request = DummyRequest(body)

    response = await webhook.zoom_webhook(request)

    assert response.plainToken == "plain-token"
    assert response.encryptedToken == hmac.new(
        b"secret-token",
        b"plain-token",
        hashlib.sha256,
    ).hexdigest()


@pytest.mark.asyncio
async def test_zoom_webhook_continues_when_signature_is_invalid(monkeypatch):
    monkeypatch.setattr(webhook, "verify_zoom_signature", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        webhook,
        "handle_meeting_ended",
        AsyncMock(return_value={"meeting_id": "123", "status": "ended", "terminated_sessions": 1}),
    )

    body = json.dumps({"event": "meeting.ended", "payload": {"object": {"id": "123"}}}).encode("utf-8")
    request = DummyRequest(body)

    response = await webhook.zoom_webhook(
        request,
        x_zm_request_timestamp="1700000000",
        x_zm_signature="invalid",
    )

    assert response["status"] == "success"
    assert response["event"] == "meeting.ended"
    webhook.handle_meeting_ended.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_meeting_started_dispatches_bot_when_no_active_sessions(monkeypatch):
    meeting_details = SimpleNamespace(
        join_url="https://zoom.example/join",
        password="pass-123",
        get_join_url_with_password=lambda: "https://zoom.example/join?pwd=pass-123",
    )
    monkeypatch.setattr(webhook.zoom_api_service, "get_meeting_details", AsyncMock(return_value=meeting_details))

    bot_service = SimpleNamespace(
        get_sessions_by_meeting=lambda meeting_id: [],
        dispatch_bot=AsyncMock(return_value=SimpleNamespace(id="session-1")),
    )
    install_bot_service(monkeypatch, bot_service)

    payload = {
        "object": {
            "id": 12345,
            "uuid": "uuid-1",
            "host_id": "host-1",
            "topic": "Weekly Sync",
            "start_time": "2026-03-22T10:00:00Z",
            "timezone": "Asia/Tokyo",
            "duration": 30,
        }
    }

    result = await webhook.handle_meeting_started(payload)

    assert result.meeting_id == "12345"
    assert result.join_url_with_password == "https://zoom.example/join?pwd=pass-123"
    bot_service.dispatch_bot.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_meeting_started_skips_dispatch_when_active_session_exists(monkeypatch):
    meeting_details = SimpleNamespace(
        join_url="https://zoom.example/join",
        password="pass-123",
        get_join_url_with_password=lambda: "https://zoom.example/join?pwd=pass-123",
    )
    monkeypatch.setattr(webhook.zoom_api_service, "get_meeting_details", AsyncMock(return_value=meeting_details))

    active_session = SimpleNamespace(status=SimpleNamespace(value="running"))
    bot_service = SimpleNamespace(
        get_sessions_by_meeting=lambda meeting_id: [active_session],
        dispatch_bot=AsyncMock(),
    )
    install_bot_service(monkeypatch, bot_service)

    payload = {"object": {"id": 12345, "uuid": "uuid-1", "host_id": "host-1", "topic": "Weekly Sync", "start_time": "2026-03-22T10:00:00Z"}}

    result = await webhook.handle_meeting_started(payload)

    assert result.meeting_id == "12345"
    bot_service.dispatch_bot.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_meeting_ended_terminates_related_sessions(monkeypatch):
    bot_service = SimpleNamespace(
        terminate_sessions_by_meeting_id=AsyncMock(return_value=2)
    )
    install_bot_service(monkeypatch, bot_service)

    payload = {"object": {"id": "meeting-1", "topic": "Weekly Sync"}}

    result = await webhook.handle_meeting_ended(payload)

    assert result == {
        "meeting_id": "meeting-1",
        "status": "ended",
        "terminated_sessions": 2,
    }
    bot_service.terminate_sessions_by_meeting_id.assert_awaited_once_with("meeting-1")
