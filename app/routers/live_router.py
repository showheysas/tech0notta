"""
ライブ文字起こしAPIエンドポイント
リアルタイム文字起こしセグメントの取得・送信用REST API
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, File, UploadFile, Form
from pydantic import BaseModel

from app.services.live_transcription_service import (
    live_transcription_service,
    TranscriptSegment,
)
from app.services.bot_service import bot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["live"])


# ==================== Request/Response Models ====================

class PushSegmentRequest(BaseModel):
    """セグメント送信リクエスト"""
    speaker: str
    text: str
    time: Optional[str] = None
    speaker_id: Optional[str] = None  # Azureからのspeaker_id


class SegmentResponse(BaseModel):
    """セグメントレスポンス"""
    id: str
    speaker: str
    speakerId: Optional[str] = None
    text: str
    time: str
    initials: str
    colorClass: str


class SessionInfoResponse(BaseModel):
    """セッション情報レスポンス"""
    session_id: str
    meeting_id: str
    meeting_topic: str
    started_at: str
    participant_count: int
    segment_count: int


class SegmentsResponse(BaseModel):
    """セグメント一覧レスポンス"""
    session: SessionInfoResponse
    segments: list[SegmentResponse]
    total_count: int


# ==================== API Endpoints ====================

@router.get("/sessions")
async def get_live_sessions():
    """
    アクティブなライブセッション一覧を取得
    """
    sessions = live_transcription_service.get_active_sessions()
    return [s.to_dict() for s in sessions]


@router.get("/segments/{session_id}", response_model=SegmentsResponse)
async def get_segments(
    session_id: str,
    since_id: Optional[str] = Query(None, description="このID以降のセグメントを取得"),
    limit: int = Query(100, ge=1, le=500, description="最大取得数")
):
    """
    セッションの文字起こしセグメントを取得
    
    Args:
        session_id: セッションID
        since_id: このID以降のセグメントを取得（差分取得用）
        limit: 最大取得数
    
    Returns:
        セグメント一覧
    """
    session = live_transcription_service.get_session(session_id)
    
    if not session:
        # セッションが存在しない場合、bot_serviceからセッションを探して自動作成
        bot_session = bot_service.get_session(session_id)
        if bot_session:
            session = live_transcription_service.create_session(
                session_id=session_id,
                meeting_id=bot_session.meeting_id,
                meeting_topic=f"会議 {bot_session.meeting_id}"
            )
        else:
            raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
    segments = live_transcription_service.get_segments(
        session_id=session_id,
        since_id=since_id,
        limit=limit
    )
    
    return SegmentsResponse(
        session=SessionInfoResponse(
            session_id=session.session_id,
            meeting_id=session.meeting_id,
            meeting_topic=session.meeting_topic,
            started_at=session.started_at.isoformat(),
            participant_count=session.participant_count,
            segment_count=len(session.segments)
        ),
        segments=[
            SegmentResponse(
                id=seg.id,
                speaker=seg.speaker,
                speakerId=seg.speaker_id,
                text=seg.text,
                time=seg.time,
                initials=seg.initials,
                colorClass=seg.color_class
            )
            for seg in segments
        ],
        total_count=len(session.segments)
    )


@router.post("/segments/{session_id}/push")
async def push_segment(session_id: str, request: PushSegmentRequest):
    """
    Botからセグメントを受信
    
    Args:
        session_id: セッションID
        request: セグメントデータ
    
    Returns:
        追加されたセグメント
    """
    # セッションが存在しない場合は自動作成
    session = live_transcription_service.get_session(session_id)
    
    if not session:
        # bot_serviceからセッション情報を取得して自動作成
        bot_session = bot_service.get_session(session_id)
        if bot_session:
            session = live_transcription_service.create_session(
                session_id=session_id,
                meeting_id=bot_session.meeting_id,
                meeting_topic=f"会議 {bot_session.meeting_id}"
            )
        else:
            # bot_sessionがなくてもライブセッションは作成可能
            session = live_transcription_service.create_session(
                session_id=session_id,
                meeting_id="unknown",
                meeting_topic="不明な会議"
            )
    
    segment = live_transcription_service.add_segment(
        session_id=session_id,
        speaker=request.speaker,
        text=request.text,
        time_str=request.time,
        speaker_id=request.speaker_id or ""
    )
    
    if not segment:
        raise HTTPException(status_code=500, detail="セグメントの追加に失敗しました")
    
    logger.info(
        f"📝 セグメント受信: session={session_id}, "
        f"speaker={request.speaker}, text={request.text[:30]}..."
    )
    
    return {
        "success": True,
        "segment": segment.to_dict()
    }


@router.post("/segments/{session_id}/init")
async def init_session(
    session_id: str,
    meeting_id: str = "",
    meeting_topic: str = ""
):
    """
    ライブセッションを初期化（Bot起動時に呼び出し）
    
    Args:
        session_id: セッションID
        meeting_id: 会議ID
        meeting_topic: 会議トピック
    """
    # 既存セッションがあれば何もしない
    existing = live_transcription_service.get_session(session_id)
    if existing:
        return {"success": True, "session": existing.to_dict(), "created": False}
    
    session = live_transcription_service.create_session(
        session_id=session_id,
        meeting_id=meeting_id,
        meeting_topic=meeting_topic or f"会議 {meeting_id}"
    )
    
    return {"success": True, "session": session.to_dict(), "created": True}


@router.delete("/segments/{session_id}")
async def clear_session(session_id: str):
    """
    セッションを削除
    """
    success = live_transcription_service.clear_session(session_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
    return {"success": True, "message": "セッションを削除しました"}


# ==================== 話者マッピングAPI ====================

class SpeakerMappingRequest(BaseModel):
    """話者マッピングリクエスト"""
    mapping: dict[str, str]  # speaker_id -> 表示名


@router.get("/speakers/{session_id}")
async def get_speakers(session_id: str):
    """
    セッション内のユニークな話者一覧を取得
    """
    session = live_transcription_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
    speakers = live_transcription_service.get_unique_speakers(session_id)
    mapping = live_transcription_service.get_speaker_mapping(session_id)
    
    return {
        "speakers": speakers,
        "mapping": mapping
    }


@router.put("/speakers/{session_id}")
async def set_speaker_mapping(session_id: str, request: SpeakerMappingRequest):
    """
    話者マッピングを設定
    
    リクエスト例:
    {
        "mapping": {
            "Guest-1": "田中太郎",
            "Guest-2": "佐藤花子"
        }
    }
    """
    success = live_transcription_service.set_speaker_mapping(session_id, request.mapping)
    
    if not success:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    
    return {"success": True, "mapping": request.mapping}



# ==================== 話者別音声データ受信 ====================

# 参加者マップ (userId -> userName) をメモリ上で保持
_participant_map: dict[int, str] = {}


class ParticipantChangeRequest(BaseModel):
    """参加者変更リクエスト"""
    user_id: int
    user_name: str
    action: str  # "join" or "leave"


@router.post("/participant")
async def participant_change(request: ParticipantChangeRequest):
    """
    参加者の入退室を受信（Botから呼び出し）
    
    Args:
        request: 参加者変更情報
    """
    global _participant_map
    
    if request.action == "join":
        _participant_map[request.user_id] = request.user_name
        logger.info(f"👋 参加者入室: id={request.user_id}, name={request.user_name}")
    elif request.action == "leave":
        if request.user_id in _participant_map:
            del _participant_map[request.user_id]
        logger.info(f"👋 参加者退室: id={request.user_id}")
    
    return {"success": True, "participants": len(_participant_map)}


@router.get("/participants")
async def get_participants():
    """
    現在の参加者一覧を取得
    """
    return {
        "participants": [
            {"user_id": uid, "user_name": name}
            for uid, name in _participant_map.items()
        ],
        "count": len(_participant_map)
    }


@router.post("/audio")
async def receive_audio(
    user_id: int = Form(...),
    user_name: str = Form(...),
    audio_data: UploadFile = File(...)
):
    """
    話者別の音声データを受信（Botから呼び出し）
    
    PCM 16LE, 16kHz の生音声データを受信し、Azure Speechで文字起こしを行う
    
    Args:
        user_id: Zoom参加者ID
        user_name: 参加者名
        audio_data: PCM音声データ（バイナリ）
    """
    try:
        # 音声データを読み込み
        audio_bytes = await audio_data.read()
        
        if len(audio_bytes) < 1600:  # 0.05秒未満は無視
            return {"success": True, "skipped": True, "reason": "too_short"}
        
        logger.debug(f"🎤 音声受信: user_id={user_id}, name={user_name}, size={len(audio_bytes)} bytes")
        
        # この音声データをAzure Speechに送信して文字起こし
        # TODO: Azure Speech SDK を使ってストリーミング認識を実装
        # 現時点では、realtime_transcriber.py の方式を使用
        
        # 参加者マップを更新
        _participant_map[user_id] = user_name
        
        return {
            "success": True,
            "user_id": user_id,
            "user_name": user_name,
            "audio_size": len(audio_bytes)
        }
        
    except Exception as e:
        logger.error(f"音声データ受信エラー: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """ライブ文字起こしサービスのヘルスチェック"""
    active_sessions = len(live_transcription_service.get_active_sessions())
    return {
        "status": "healthy",
        "service": "live-transcription",
        "active_sessions": active_sessions,
        "participants": len(_participant_map)
    }
