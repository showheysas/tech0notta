"""
Bot派遣APIエンドポイント
Bot派遣・状態確認・退出のREST API
"""
import logging
from typing import Optional

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.bot_service import bot_service, BotStatus, BotPlatform

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bot", tags=["bot"])


# ==================== Request/Response Models ====================

class DispatchBotRequest(BaseModel):
    """Bot派遣リクエスト"""
    meeting_id: str  # 会議ID or URL
    password: Optional[str] = None  # 会議パスワード（Zoomのみ）
    meeting_url: Optional[str] = None  # 会議URL（Google Meet / Teams で使用）


class BotSessionResponse(BaseModel):
    """Botセッションレスポンス"""
    id: str
    meeting_id: str
    status: str
    created_at: str
    updated_at: str
    container_id: Optional[str] = None
    error_message: Optional[str] = None
    platform: str = "zoom"
    meeting_url: Optional[str] = None


class DispatchBotResponse(BaseModel):
    """Bot派遣レスポンス"""
    success: bool
    session: Optional[BotSessionResponse] = None
    message: Optional[str] = None


class TerminateBotResponse(BaseModel):
    """Bot退出レスポンス"""
    success: bool
    message: str


# ==================== API Endpoints ====================

@router.post("/dispatch", response_model=DispatchBotResponse)
async def dispatch_bot(request: DispatchBotRequest):
    """
    Botを会議に派遣
    
    Args:
        request: 会議ID（URL可）とパスワード
    
    Returns:
        セッション情報
    """
    logger.info(
        f"Bot派遣リクエスト: meeting_id={request.meeting_id}"
    )
    
    try:
        session = await bot_service.dispatch_bot(
            meeting_id=request.meeting_id,
            password=request.password,
            meeting_url=request.meeting_url,
        )
        
        return DispatchBotResponse(
            success=True,
            session=BotSessionResponse(**session.to_dict()),
            message="Bot派遣を開始しました"
        )
        
    except ValueError as e:
        logger.error(f"Bot派遣失敗: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Bot派遣中にエラーが発生: {e}")
        raise HTTPException(status_code=500, detail="Bot派遣中にエラーが発生しました")


@router.get("/{session_id}/status", response_model=BotSessionResponse)
async def get_bot_status(session_id: str):
    """
    Botセッションの状態を取得
    
    Args:
        session_id: セッションID
    
    Returns:
        セッション情報
    """
    session = bot_service.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
    return BotSessionResponse(**session.to_dict())


@router.post("/{session_id}/terminate", response_model=TerminateBotResponse)
async def terminate_bot(session_id: str):
    """
    Botを会議から退出させる
    
    Args:
        session_id: セッションID
    
    Returns:
        結果
    """
    logger.info(f"Bot退出リクエスト: session_id={session_id}")
    
    success = await bot_service.terminate_bot(session_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail="セッションが見つからないか、既に終了しています"
        )
    
    return TerminateBotResponse(
        success=True,
        message="Botを退出させました"
    )


@router.post("/{session_id}/complete")
async def complete_bot_session(session_id: str):
    """
    ACIコンテナが会議から自然退出したときに呼び出す。
    ステータスをCOMPLETEDに更新し、フロントエンドの自動終了フローを起動させる。
    """
    session = bot_service.get_session(session_id)
    if session and session.status not in (BotStatus.COMPLETED, BotStatus.ERROR):
        session.status = BotStatus.COMPLETED
        session.updated_at = datetime.utcnow()
        logger.info(f"✅ Bot自然終了を記録: session_id={session_id}")
    return {"success": True, "message": "状態をCOMPLETEDに更新しました"}


@router.get("/{session_id}/logs")
async def get_bot_logs(session_id: str):
    """
    ACI コンテナのログを取得（デバッグ用）
    """
    session = bot_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")

    logs = await bot_service.get_bot_logs(session_id)
    return {"session_id": session_id, "container_id": session.container_id, "logs": logs}


@router.get("/sessions", response_model=list[BotSessionResponse])
async def get_active_sessions():
    """
    アクティブなセッション一覧を取得
    """
    sessions = bot_service.get_active_sessions()
    return [BotSessionResponse(**s.to_dict()) for s in sessions]


@router.get("/health")
async def health_check():
    """Bot派遣サービスのヘルスチェック"""
    from app.services.sdk_jwt_service import sdk_jwt_service
    
    return {
        "status": "healthy",
        "service": "bot-dispatch",
        "sdk_configured": sdk_jwt_service.is_configured()
    }
