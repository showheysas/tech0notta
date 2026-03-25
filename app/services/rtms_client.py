"""
Zoom RTMS (Real-time Media Streams) クライアント

Zoom RTMSゲートウェイに接続し、参加者ごとの音声・文字起こしストリームを受信する
"""
import asyncio
import json
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass

import websockets
from websockets.client import WebSocketClientProtocol

from app.services.live_transcription_service import live_transcription_service

logger = logging.getLogger(__name__)


@dataclass
class RTMSSession:
    """RTMSセッション情報"""
    meeting_id: str
    meeting_topic: str
    stream_url: str
    signaling_url: str
    session_id: str
    websocket: Optional[WebSocketClientProtocol] = None
    is_connected: bool = False
    task: Optional[asyncio.Task] = None


class RTMSManager:
    """
    RTMSセッションマネージャー
    
    複数のRTMSセッションを管理し、各セッションからの
    音声・文字起こしデータを処理する
    """
    
    def __init__(self):
        self._sessions: Dict[str, RTMSSession] = {}
    
    async def start_session(
        self,
        meeting_id: str,
        meeting_topic: str,
        stream_url: str,
        signaling_url: str
    ) -> str:
        """
        RTMSセッションを開始
        
        Args:
            meeting_id: ミーティングID
            meeting_topic: ミーティングトピック
            stream_url: RTMSストリームURL
            signaling_url: RTMSシグナリングURL
        
        Returns:
            セッションID
        """
        # セッションIDを生成
        session_id = f"rtms-{meeting_id}"
        
        # 既存セッションがあれば停止
        if meeting_id in self._sessions:
            await self.stop_session(meeting_id)
        
        # ライブ文字起こしセッションを作成
        live_transcription_service.create_session(
            session_id=session_id,
            meeting_id=meeting_id,
            meeting_topic=meeting_topic
        )
        
        # RTMSセッションを作成
        session = RTMSSession(
            meeting_id=meeting_id,
            meeting_topic=meeting_topic,
            stream_url=stream_url,
            signaling_url=signaling_url,
            session_id=session_id
        )
        self._sessions[meeting_id] = session
        
        # WebSocket接続を開始（バックグラウンドタスク）
        session.task = asyncio.create_task(
            self._run_session(session)
        )
        
        logger.info(f"🎙️ RTMSセッション開始: session_id={session_id}")
        return session_id
    
    async def stop_session(self, meeting_id: str) -> None:
        """RTMSセッションを停止"""
        session = self._sessions.get(meeting_id)
        if not session:
            return
        
        logger.info(f"🛑 RTMSセッション停止: session_id={session.session_id}")
        
        # WebSocket接続を閉じる
        if session.websocket and session.is_connected:
            try:
                await session.websocket.close()
            except Exception as e:
                logger.warning(f"WebSocket close error: {e}")
        
        # タスクをキャンセル
        if session.task and not session.task.done():
            session.task.cancel()
            try:
                await session.task
            except asyncio.CancelledError:
                pass
        
        # ライブセッションを終了（削除はしない、履歴として残す）
        # live_transcription_service.clear_session(session.session_id)
        
        del self._sessions[meeting_id]
    
    async def _run_session(self, session: RTMSSession) -> None:
        """RTMSセッションのWebSocket接続を実行"""
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                logger.info(f"🔌 RTMS WebSocket接続中: {session.stream_url}")
                
                async with websockets.connect(
                    session.stream_url,
                    ping_interval=30,
                    ping_timeout=10
                ) as websocket:
                    session.websocket = websocket
                    session.is_connected = True
                    logger.info(f"✅ RTMS WebSocket接続成功")
                    
                    # メッセージ受信ループ
                    await self._receive_loop(session, websocket)
                    
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ RTMS WebSocket接続が閉じられました: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(2 ** retry_count)  # 指数バックオフ
                    
            except asyncio.CancelledError:
                logger.info("RTMSセッションがキャンセルされました")
                break
                
            except Exception as e:
                logger.error(f"❌ RTMS WebSocket接続エラー: {e}", exc_info=True)
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(2 ** retry_count)
        
        session.is_connected = False
    
    async def _receive_loop(
        self,
        session: RTMSSession,
        websocket: WebSocketClientProtocol
    ) -> None:
        """WebSocketメッセージ受信ループ"""
        async for message in websocket:
            try:
                await self._handle_message(session, message)
            except Exception as e:
                logger.error(f"メッセージ処理エラー: {e}", exc_info=True)
    
    async def _handle_message(self, session: RTMSSession, message: str | bytes) -> None:
        """
        RTMSメッセージを処理
        
        メッセージ種別:
        - audio: 音声データ（PCM）
        - transcript: リアルタイム文字起こし
        - participant: 参加者情報
        """
        if isinstance(message, bytes):
            # バイナリメッセージ（音声データなど）
            # ここでは音声データは処理せず、transcriptを直接使用
            return
        
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message: {message[:100]}")
            return
        
        msg_type = data.get("type", "")
        
        if msg_type == "transcript":
            await self._handle_transcript(session, data)
        elif msg_type == "audio":
            await self._handle_audio(session, data)
        elif msg_type == "participant":
            await self._handle_participant(session, data)
        else:
            logger.debug(f"未処理のメッセージタイプ: {msg_type}")
    
    async def _handle_transcript(self, session: RTMSSession, data: Dict[str, Any]) -> None:
        """
        文字起こしメッセージを処理
        
        話者情報付きでセグメントを追加
        """
        text = data.get("text", "")
        user_name = data.get("userName", data.get("user_name", "参加者"))
        user_id = data.get("userId", data.get("user_id", ""))
        is_final = data.get("isFinal", data.get("is_final", True))
        
        # 確定テキストのみを処理（中間結果はスキップ）
        if not is_final or not text.strip():
            return
        
        logger.info(f"📝 文字起こし受信: [{user_name}] {text[:50]}...")
        
        # セグメントを追加
        live_transcription_service.add_segment(
            session_id=session.session_id,
            speaker=user_name,
            text=text
        )
    
    async def _handle_audio(self, session: RTMSSession, data: Dict[str, Any]) -> None:
        """
        音声データを処理
        
        注: RTMSからtranscriptが直接提供されるため、
        音声データの個別処理は現時点では不要
        """
        # 必要に応じて音声データをAzure Speechに送信して
        # 独自の文字起こしを行うことも可能
        pass
    
    async def _handle_participant(self, session: RTMSSession, data: Dict[str, Any]) -> None:
        """参加者情報を処理"""
        action = data.get("action", "")
        user_name = data.get("userName", "")
        participants = data.get("participants", [])
        
        if action == "join":
            logger.info(f"👋 参加者入室: {user_name}")
        elif action == "leave":
            logger.info(f"👋 参加者退室: {user_name}")
        
        # 参加者数を更新
        if participants:
            live_transcription_service.update_participant_count(
                session.session_id,
                len(participants)
            )
    
    def get_active_sessions(self) -> list:
        """アクティブなセッションのリストを取得"""
        return [
            {
                "meeting_id": s.meeting_id,
                "meeting_topic": s.meeting_topic,
                "session_id": s.session_id,
                "is_connected": s.is_connected
            }
            for s in self._sessions.values()
        ]


# シングルトンインスタンス
rtms_manager = RTMSManager()
