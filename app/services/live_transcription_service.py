"""
リアルタイム文字起こしサービス
セッションごとにリアルタイムの文字起こしセグメントを管理する
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import uuid

from app.timezone import jst_now

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    """文字起こしセグメント"""
    id: str
    speaker: str
    text: str
    time: str
    timestamp: datetime
    speaker_id: str = ""  # Azureからのspeaker_id（マッピング用）
    initials: str = ""
    color_class: str = ""
    
    def __post_init__(self):
        # initials が空の場合は speaker から自動生成
        if not self.initials and self.speaker:
            # 日本語名の場合は最初の2文字
            self.initials = self.speaker[:2] if self.speaker else ""
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "speaker": self.speaker,
            "speakerId": self.speaker_id,
            "text": self.text,
            "time": self.time,
            "initials": self.initials,
            "colorClass": self.color_class,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class LiveSession:
    """ライブセッション"""
    session_id: str
    meeting_id: str
    meeting_topic: str
    started_at: datetime
    segments: List[TranscriptSegment] = field(default_factory=list)
    participant_count: int = 0
    speaker_mapping: Dict[str, str] = field(default_factory=dict)  # speaker_id -> ユーザー指定の名前
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "meeting_id": self.meeting_id,
            "meeting_topic": self.meeting_topic,
            "started_at": self.started_at.isoformat(),
            "participant_count": self.participant_count,
            "segment_count": len(self.segments),
            "speaker_mapping": self.speaker_mapping
        }


# スピーカーごとの色クラス（ローテーション）
SPEAKER_COLORS = [
    "bg-blue-100 text-blue-700",
    "bg-emerald-100 text-emerald-700",
    "bg-purple-100 text-purple-700",
    "bg-amber-100 text-amber-700",
    "bg-rose-100 text-rose-700",
    "bg-cyan-100 text-cyan-700",
]


class LiveTranscriptionService:
    """リアルタイム文字起こしサービス"""
    
    def __init__(self):
        # セッションID -> LiveSession のマップ
        self._sessions: Dict[str, LiveSession] = {}
        # スピーカー名 -> 色クラスのマップ（セッションごと）
        self._speaker_colors: Dict[str, Dict[str, str]] = {}
    
    def create_session(
        self,
        session_id: str,
        meeting_id: str,
        meeting_topic: str = ""
    ) -> LiveSession:
        """
        新しいライブセッションを作成
        """
        session = LiveSession(
            session_id=session_id,
            meeting_id=meeting_id,
            meeting_topic=meeting_topic or f"会議 {meeting_id}",
            started_at=jst_now()
        )
        self._sessions[session_id] = session
        self._speaker_colors[session_id] = {}
        
        logger.info(f"🎙️ ライブセッション作成: session_id={session_id}, meeting_id={meeting_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[LiveSession]:
        """
        セッションを取得
        """
        return self._sessions.get(session_id)
    
    def _get_speaker_color(self, session_id: str, speaker: str) -> str:
        """
        スピーカーの色クラスを取得（なければ新規割り当て）
        """
        if session_id not in self._speaker_colors:
            self._speaker_colors[session_id] = {}
        
        colors = self._speaker_colors[session_id]
        
        if speaker not in colors:
            # 新しいスピーカーに色を割り当て
            color_index = len(colors) % len(SPEAKER_COLORS)
            colors[speaker] = SPEAKER_COLORS[color_index]
        
        return colors[speaker]
    
    def add_segment(
        self,
        session_id: str,
        speaker: str,
        text: str,
        time_str: Optional[str] = None,
        speaker_id: str = ""
    ) -> Optional[TranscriptSegment]:
        """
        セグメントを追加
        
        Args:
            session_id: セッションID
            speaker: 発話者名
            text: 発話テキスト
            time_str: 時刻文字列（省略時は現在時刻）
            speaker_id: Azureからのspeaker_id
        
        Returns:
            追加されたセグメント、セッションが見つからない場合はNone
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"セッションが見つかりません: {session_id}")
            return None
        
        now = jst_now()
        
        # 話者マッピングがあれば適用
        display_speaker = speaker
        if speaker_id and session.speaker_mapping.get(speaker_id):
            display_speaker = session.speaker_mapping[speaker_id]
        
        segment = TranscriptSegment(
            id=str(uuid.uuid4()),
            speaker=display_speaker,
            speaker_id=speaker_id,
            text=text,
            time=time_str or now.strftime("%H:%M"),
            timestamp=now,
            color_class=self._get_speaker_color(session_id, speaker_id or speaker)
        )
        
        session.segments.append(segment)
        
        logger.debug(
            f"セグメント追加: session={session_id}, speaker={display_speaker}, "
            f"text={text[:30]}..."
        )
        
        return segment
    
    def get_segments(
        self,
        session_id: str,
        since_id: Optional[str] = None,
        limit: int = 100
    ) -> List[TranscriptSegment]:
        """
        セグメントを取得
        
        Args:
            session_id: セッションID
            since_id: このID以降のセグメントを取得（差分取得用）
            limit: 最大取得数
        
        Returns:
            セグメントリスト
        """
        session = self._sessions.get(session_id)
        if not session:
            return []
        
        segments = session.segments
        
        # since_id が指定された場合、その ID 以降のセグメントを返す
        if since_id:
            found_index = -1
            for i, seg in enumerate(segments):
                if seg.id == since_id:
                    found_index = i
                    break
            
            if found_index >= 0:
                segments = segments[found_index + 1:]
        
        # limit 適用
        return segments[-limit:] if len(segments) > limit else segments
    
    def update_participant_count(self, session_id: str, count: int) -> None:
        """
        参加者数を更新
        """
        session = self._sessions.get(session_id)
        if session:
            session.participant_count = count
    
    def clear_session(self, session_id: str) -> bool:
        """
        セッションをクリア
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            if session_id in self._speaker_colors:
                del self._speaker_colors[session_id]
            logger.info(f"🗑️ ライブセッション削除: session_id={session_id}")
            return True
        return False
    
    def get_active_sessions(self) -> List[LiveSession]:
        """
        アクティブなセッション一覧を取得
        """
        return list(self._sessions.values())
    
    def set_speaker_mapping(
        self,
        session_id: str,
        mapping: Dict[str, str]
    ) -> bool:
        """
        話者マッピングを設定
        
        Args:
            session_id: セッションID
            mapping: speaker_id -> 表示名 のマップ
        
        Returns:
            成功/失敗
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"セッションが見つかりません: {session_id}")
            return False
        
        session.speaker_mapping = mapping
        
        # 既存セグメントの話者名も更新
        for segment in session.segments:
            if segment.speaker_id and segment.speaker_id in mapping:
                segment.speaker = mapping[segment.speaker_id]
                segment.initials = segment.speaker[:2] if segment.speaker else ""
        
        logger.info(f"🔄 話者マッピング更新: session={session_id}, mapping={mapping}")
        return True
    
    def get_speaker_mapping(self, session_id: str) -> Dict[str, str]:
        """
        話者マッピングを取得
        """
        session = self._sessions.get(session_id)
        if not session:
            return {}
        return session.speaker_mapping
    
    def get_unique_speakers(self, session_id: str) -> List[dict]:
        """
        セッション内のユニークな話者一覧を取得
        
        Returns:
            [{"speaker_id": "...", "label": "話者1", "mapped_name": "田中"}]
        """
        session = self._sessions.get(session_id)
        if not session:
            return []
        
        speakers = {}
        for segment in session.segments:
            sid = segment.speaker_id or segment.speaker
            if sid not in speakers:
                speakers[sid] = {
                    "speaker_id": segment.speaker_id,
                    "label": segment.speaker,
                    "mapped_name": session.speaker_mapping.get(segment.speaker_id, "")
                }
        
        return list(speakers.values())


# シングルトンインスタンス
live_transcription_service = LiveTranscriptionService()
