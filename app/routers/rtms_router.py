"""
Zoom RTMS (Real-time Media Streams) ルーター

Zoom RTMS Webhookを受信し、RTMSクライアントを起動する
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import hmac
import hashlib
import json

from app.config import settings
from app.services.rtms_client import rtms_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rtms", tags=["rtms"])


class RTMSWebhookPayload(BaseModel):
    """RTMS Webhookペイロード"""
    event: str
    payload: Dict[str, Any]


def verify_webhook_signature(request_body: bytes, signature: str, timestamp: str) -> bool:
    """Zoom Webhook署名を検証"""
    if not settings.ZOOM_WEBHOOK_SECRET_TOKEN:
        logger.warning("ZOOM_WEBHOOK_SECRET_TOKEN が設定されていません")
        return True  # 開発環境では検証をスキップ
    
    message = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    expected_signature = "v0=" + hmac.new(
        settings.ZOOM_WEBHOOK_SECRET_TOKEN.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


@router.post("/webhook")
async def rtms_webhook(request: Request):
    """
    Zoom RTMS Webhookエンドポイント
    
    受信するイベント:
    - rtms.started: RTMSセッション開始（WebSocket接続情報を含む）
    - rtms.stopped: RTMSセッション終了
    """
    body = await request.body()
    
    # 署名検証
    signature = request.headers.get("x-zm-signature", "")
    timestamp = request.headers.get("x-zm-request-timestamp", "")
    
    if not verify_webhook_signature(body, signature, timestamp):
        logger.warning("❌ RTMS Webhook署名検証失敗")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event = data.get("event", "")
    payload = data.get("payload", {})
    
    logger.info(f"📡 RTMS Webhook受信: event={event}")
    
    # URL検証チャレンジ（初回登録時）
    if event == "endpoint.url_validation":
        plain_token = payload.get("plainToken", "")
        if settings.ZOOM_WEBHOOK_SECRET_TOKEN:
            encrypted_token = hmac.new(
                settings.ZOOM_WEBHOOK_SECRET_TOKEN.encode('utf-8'),
                plain_token.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            return {
                "plainToken": plain_token,
                "encryptedToken": encrypted_token
            }
        return {"plainToken": plain_token, "encryptedToken": ""}
    
    # RTMS開始イベント
    if event == "rtms.started":
        await handle_rtms_started(payload)
    
    # RTMS終了イベント
    elif event == "rtms.stopped":
        await handle_rtms_stopped(payload)
    
    return {"status": "ok"}


async def handle_rtms_started(payload: Dict[str, Any]):
    """
    RTMS開始イベントを処理
    
    WebSocket接続情報を取得し、RTMSクライアントを起動
    """
    object_data = payload.get("object", {})
    meeting_id = object_data.get("meeting_id", "")
    meeting_topic = object_data.get("meeting_topic", "")
    start_time = object_data.get("start_time", "")
    
    # RTMS接続情報
    rtms_data = object_data.get("rtms", {})
    stream_url = rtms_data.get("stream_url", "")
    signaling_url = rtms_data.get("signaling_url", "")
    
    logger.info(f"🚀 RTMS開始: meeting_id={meeting_id}, topic={meeting_topic}")
    logger.info(f"   Stream URL: {stream_url}")
    logger.info(f"   Signaling URL: {signaling_url}")
    
    if stream_url:
        # RTMSクライアントを起動
        await rtms_manager.start_session(
            meeting_id=meeting_id,
            meeting_topic=meeting_topic,
            stream_url=stream_url,
            signaling_url=signaling_url
        )


async def handle_rtms_stopped(payload: Dict[str, Any]):
    """
    RTMS終了イベントを処理
    """
    object_data = payload.get("object", {})
    meeting_id = object_data.get("meeting_id", "")
    
    logger.info(f"🛑 RTMS終了: meeting_id={meeting_id}")
    
    await rtms_manager.stop_session(meeting_id)
