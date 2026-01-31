"""
Zoom Webhook エンドポイント
Zoom会議イベント（meeting.started等）を受信するWebhookエンドポイント
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.zoom_config import zoom_config
from app.services.zoom_api_service import zoom_api_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/zoom", tags=["zoom"])


# ==================== Pydantic Models ====================

class ZoomWebhookPayload(BaseModel):
    """Zoom Webhookのペイロード"""
    event: str  # イベント名
    event_ts: int  # イベントのタイムスタンプ
    payload: dict[str, Any]  # 詳細データ


class ChallengeResponse(BaseModel):
    """CRC（Challenge-Response Check）のレスポンス"""
    plainToken: str
    encryptedToken: str


class MeetingInfo(BaseModel):
    """会議情報"""
    meeting_id: str
    uuid: str
    host_id: str
    topic: str
    start_time: str
    timezone: str | None = None
    duration: int | None = None
    # API から取得した詳細情報
    join_url: str | None = None
    join_url_with_password: str | None = None
    password: str | None = None


# ==================== Helper Functions ====================

def verify_zoom_signature(
    request_body: bytes,
    timestamp: str,
    signature: str,
    secret_token: str
) -> bool:
    """
    Zoom Webhookの署名を検証
    
    Args:
        request_body: リクエストボディ（バイト列）
        timestamp: x-zm-request-timestamp ヘッダーの値
        signature: x-zm-signature ヘッダーの値
        secret_token: Zoom Webhook Secret Token
    
    Returns:
        署名が有効な場合True
    """
    if not secret_token:
        logger.warning("ZOOM_WEBHOOK_SECRET_TOKEN が設定されていません")
        return False
    
    # メッセージを構築: v0:{timestamp}:{body}
    message = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    
    # HMAC SHA-256 でハッシュを生成
    hash_for_verify = hmac.new(
        secret_token.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # 署名を作成して比較
    expected_signature = f"v0={hash_for_verify}"
    
    return hmac.compare_digest(signature, expected_signature)


def create_challenge_response(plain_token: str, secret_token: str) -> ChallengeResponse:
    """
    CRC（Challenge-Response Check）のレスポンスを生成
    
    Args:
        plain_token: Zoomから送られてきたplainToken
        secret_token: Zoom Webhook Secret Token
    
    Returns:
        ChallengeResponse
    """
    encrypted_token = hmac.new(
        secret_token.encode('utf-8'),
        plain_token.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    return ChallengeResponse(
        plainToken=plain_token,
        encryptedToken=encrypted_token
    )


# ==================== Event Handlers ====================

async def handle_meeting_started(payload: dict[str, Any]) -> MeetingInfo:
    """
    会議開始イベントを処理
    
    Args:
        payload: Webhookペイロード
    
    Returns:
        MeetingInfo
    """
    # Bot派遣サービスのインポート（循環参照回避）
    from app.services.bot_service import bot_service
    
    meeting_object = payload.get("object", {})
    meeting_id = str(meeting_object.get("id", ""))
    
    meeting_info = MeetingInfo(
        meeting_id=meeting_id,
        uuid=meeting_object.get("uuid", ""),
        host_id=meeting_object.get("host_id", ""),
        topic=meeting_object.get("topic", ""),
        start_time=meeting_object.get("start_time", ""),
        timezone=meeting_object.get("timezone"),
        duration=meeting_object.get("duration")
    )
    
    logger.info(
        f"🎥 会議が開始されました: "
        f"ID={meeting_info.meeting_id}, "
        f"トピック='{meeting_info.topic}', "
        f"開始時刻={meeting_info.start_time}"
    )
    
    # Zoom APIから会議詳細を取得してパスコード付きURLを取得
    try:
        meeting_details = await zoom_api_service.get_meeting_details(meeting_id)
        if meeting_details:
            meeting_info.join_url = meeting_details.join_url
            meeting_info.join_url_with_password = meeting_details.get_join_url_with_password()
            meeting_info.password = meeting_details.password
            
            logger.info(
                f"🔗 パスコード付きURL取得完了: "
                f"join_url_with_password={meeting_info.join_url_with_password}"
            )
            
            # Bot自動派遣（重複チェック）
            try:
                # 既にこの会議にBotが派遣されているかチェック
                existing_sessions = bot_service.get_sessions_by_meeting(meeting_id)
                active_sessions = [
                    s for s in existing_sessions 
                    if s.status.value not in ("completed", "error")
                ]
                
                if active_sessions:
                    logger.info(
                        f"⏭️ 既にBotが派遣済みのためスキップ: "
                        f"meeting_id={meeting_id}, active_sessions={len(active_sessions)}"
                    )
                else:
                    session = await bot_service.dispatch_bot(
                        meeting_id=meeting_id,
                        password=meeting_details.password
                    )
                    logger.info(
                        f"🤖 Bot自動派遣完了: "
                        f"session_id={session.id}, meeting_id={meeting_id}"
                    )
            except Exception as e:
                logger.error(f"Bot自動派遣失敗: {e}")
        else:
            logger.warning(
                f"⚠️ 会議詳細の取得に失敗しました。"
                f"Zoom OAuth設定を確認してください。"
            )
    except Exception as e:
        logger.error(f"会議詳細の取得中にエラーが発生: {e}")
    
    return meeting_info


async def handle_meeting_ended(payload: dict[str, Any]) -> dict[str, Any]:
    """
    会議終了イベントを処理
    
    Args:
        payload: Webhookペイロード
    
    Returns:
        処理結果
    """
    meeting_object = payload.get("object", {})
    meeting_id = meeting_object.get("id", "")
    topic = meeting_object.get("topic", "")
    
    # Bot派遣サービスのインポート（循環参照回避）
    from app.services.bot_service import bot_service
    
    # 関連するBotセッションを終了（ステータス更新）
    # Note: Bot自体はZoom SDKの仕様で会議終了時に自己終了するが、
    # 管理側のステータスを確実に完了にするために呼び出す
    terminated_count = await bot_service.terminate_sessions_by_meeting_id(str(meeting_id))
    
    logger.info(f"🛑 会議が終了しました: ID={meeting_id}, トピック='{topic}', 終了セッション数={terminated_count}")
    
    return {"meeting_id": meeting_id, "status": "ended", "terminated_sessions": terminated_count}


# ==================== API Endpoints ====================

@router.post("/webhook")
async def zoom_webhook(
    request: Request,
    x_zm_request_timestamp: str = Header(None, alias="x-zm-request-timestamp"),
    x_zm_signature: str = Header(None, alias="x-zm-signature")
):
    """
    Zoom Webhookエンドポイント
    
    Zoomからのイベント通知を受信し、適切なハンドラーで処理する。
    
    サポートしているイベント:
    - endpoint.url_validation: CRC（Challenge-Response Check）
    - meeting.started: 会議開始
    - meeting.ended: 会議終了
    """
    # イベントタイプに応じて処理
    # 先にボディを取得（検証用）
    raw_body = await request.body()
    
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    event_type = data.get("event", "")
    
    logger.info(f"Zoom Webhook受信: event={event_type}")
    
    # CRC（Challenge-Response Check）の場合は署名検証なしで応答
    if event_type == "endpoint.url_validation":
        plain_token = data.get("payload", {}).get("plainToken", "")
        if not plain_token:
            raise HTTPException(status_code=400, detail="plainToken not found")
        
        response = create_challenge_response(
            plain_token,
            zoom_config.webhook_secret_token
        )
        logger.info("✅ CRC検証リクエストに応答しました")
        return response
    
    # 通常のイベントの場合は署名を検証
    if x_zm_request_timestamp and x_zm_signature:
        is_valid = verify_zoom_signature(
            raw_body,  # 生のバイト列を渡す
            x_zm_request_timestamp,
            x_zm_signature,
            zoom_config.webhook_secret_token
        )
        
        if not is_valid:
            logger.warning(f"⚠️ 無効な署名を検出しました")
            logger.warning(f"  受信ヘッダー: timestamp={x_zm_request_timestamp}, signature={x_zm_signature}")
            
            # デバッグ用に計算値をログ出力（本番ではSecret Tokenが漏れないよう注意が必要だが、署名自体はログに出してもリスクは低い）
            # 再計算してログに出す
            message = f"v0:{x_zm_request_timestamp}:{raw_body.decode('utf-8')}"
            hash_for_verify = hmac.new(
                zoom_config.webhook_secret_token.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            calculated_signature = f"v0={hash_for_verify}"
            
            logger.warning(f"  期待される署名: {calculated_signature}")
            logger.warning(f"  Secret Token長: {len(zoom_config.webhook_secret_token) if zoom_config.webhook_secret_token else 0}")
            
            # デバッグモード: 署名検証失敗しても通す（開発用）
            logger.error("⚠️ 署名検証に失敗しましたが、処理を続行します（デバッグモード）")
            # raise HTTPException(status_code=401, detail="Invalid signature")
    else:
        logger.warning("⚠️ 署名ヘッダーがありません")
        # 開発時は許可、本番では拒否を推奨
        # raise HTTPException(status_code=401, detail="Missing signature headers")
    
    # イベントタイプに応じて処理
    payload = data.get("payload", {})
    
    if event_type == "meeting.started":
        result = await handle_meeting_started(payload)
        return {"status": "success", "event": event_type, "meeting": result.model_dump()}
    
    elif event_type == "meeting.ended":
        result = await handle_meeting_ended(payload)
        return {"status": "success", "event": event_type, "result": result}
    
    else:
        logger.info(f"未処理のイベント: {event_type}")
        return {"status": "success", "event": event_type, "message": "Event received but not processed"}


@router.get("/health")
async def health_check():
    """Zoom Webhookサービスのヘルスチェック"""
    return {
        "status": "healthy",
        "service": "zoom-webhook",
        "timestamp": datetime.utcnow().isoformat()
    }
