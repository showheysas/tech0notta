"""
話者別音声認識サービス

各参加者の音声ストリームを個別に処理し、Azure Speechで文字起こしを行う
"""
import io
import logging
import wave
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import threading
import queue

from app.timezone import jst_now

import azure.cognitiveservices.speech as speechsdk

from app.config import settings
from app.services.live_transcription_service import live_transcription_service

logger = logging.getLogger(__name__)


@dataclass
class SpeakerRecognizer:
    """話者ごとの音声認識器"""
    user_id: int
    user_name: str
    audio_buffer: queue.Queue = field(default_factory=lambda: queue.Queue())
    recognizer: Optional[speechsdk.SpeechRecognizer] = None
    push_stream: Optional[speechsdk.audio.PushAudioInputStream] = None
    is_running: bool = False
    last_activity: datetime = field(default_factory=jst_now)


class SpeakerAudioRecognitionService:
    """
    話者別音声認識サービス
    
    各参加者ごとにAzure Speech認識器を作成し、
    個別の音声ストリームを文字起こしする
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._recognizers: Dict[int, SpeakerRecognizer] = {}
        self._lock = threading.Lock()
        
        # Azure Speech設定
        self.speech_config = speechsdk.SpeechConfig(
            subscription=settings.AZURE_SPEECH_KEY,
            region=settings.AZURE_SPEECH_REGION
        )
        self.speech_config.speech_recognition_language = "ja-JP"
        
        logger.info(f"🎙️ SpeakerAudioRecognitionService created for session: {session_id}")
    
    def process_audio(self, user_id: int, user_name: str, audio_data: bytes) -> None:
        """
        話者の音声データを処理
        
        Args:
            user_id: Zoom参加者ID
            user_name: 参加者名
            audio_data: PCM 16LE, 16kHz 音声データ
        """
        with self._lock:
            if user_id not in self._recognizers:
                self._create_recognizer(user_id, user_name)
            
            recognizer = self._recognizers[user_id]
            recognizer.last_activity = jst_now()
            
            # PushStreamに音声データを送信
            if recognizer.push_stream:
                recognizer.push_stream.write(audio_data)
    
    def _create_recognizer(self, user_id: int, user_name: str) -> None:
        """話者用の認識器を作成"""
        logger.info(f"🎤 Creating recognizer for user: {user_id} ({user_name})")
        
        # PushAudioInputStream を作成（PCM 16LE, 16kHz, mono）
        audio_format = speechsdk.audio.AudioStreamFormat(
            samples_per_second=16000,
            bits_per_sample=16,
            channels=1
        )
        push_stream = speechsdk.audio.PushAudioInputStream(stream_format=audio_format)
        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
        
        # 認識器を作成
        speech_recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config,
            audio_config=audio_config
        )
        
        # コールバックを設定
        def on_recognized(evt: speechsdk.SpeechRecognitionEventArgs):
            if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = evt.result.text
                if text.strip():
                    logger.info(f"📝 [{user_name}] {text}")
                    
                    # セグメントを追加
                    live_transcription_service.add_segment(
                        session_id=self.session_id,
                        speaker=user_name,
                        text=text
                    )
        
        def on_canceled(evt: speechsdk.SpeechRecognitionCanceledEventArgs):
            if evt.reason == speechsdk.CancellationReason.Error:
                logger.error(f"❌ Recognition error for {user_name}: {evt.error_details}")
        
        speech_recognizer.recognized.connect(on_recognized)
        speech_recognizer.canceled.connect(on_canceled)
        
        # 継続的認識を開始
        speech_recognizer.start_continuous_recognition()
        
        # 認識器を保存
        self._recognizers[user_id] = SpeakerRecognizer(
            user_id=user_id,
            user_name=user_name,
            recognizer=speech_recognizer,
            push_stream=push_stream,
            is_running=True
        )
    
    def stop_recognizer(self, user_id: int) -> None:
        """話者の認識器を停止"""
        with self._lock:
            if user_id in self._recognizers:
                recognizer = self._recognizers[user_id]
                
                if recognizer.push_stream:
                    recognizer.push_stream.close()
                
                if recognizer.recognizer:
                    recognizer.recognizer.stop_continuous_recognition()
                
                recognizer.is_running = False
                del self._recognizers[user_id]
                
                logger.info(f"🛑 Recognizer stopped for user: {user_id}")
    
    def stop_all(self) -> None:
        """全ての認識器を停止"""
        with self._lock:
            user_ids = list(self._recognizers.keys())
        
        for user_id in user_ids:
            self.stop_recognizer(user_id)
        
        logger.info(f"🛑 All recognizers stopped for session: {self.session_id}")
    
    def get_active_speakers(self) -> list:
        """アクティブな話者一覧を取得"""
        with self._lock:
            return [
                {
                    "user_id": r.user_id,
                    "user_name": r.user_name,
                    "is_running": r.is_running,
                    "last_activity": r.last_activity.isoformat()
                }
                for r in self._recognizers.values()
            ]


# セッションごとのサービスインスタンス管理
_session_services: Dict[str, SpeakerAudioRecognitionService] = {}
_services_lock = threading.Lock()


def get_speaker_recognition_service(session_id: str) -> SpeakerAudioRecognitionService:
    """セッションの話者認識サービスを取得または作成"""
    global _session_services
    
    with _services_lock:
        if session_id not in _session_services:
            _session_services[session_id] = SpeakerAudioRecognitionService(session_id)
        return _session_services[session_id]


def stop_speaker_recognition_service(session_id: str) -> None:
    """セッションの話者認識サービスを停止"""
    global _session_services
    
    with _services_lock:
        if session_id in _session_services:
            _session_services[session_id].stop_all()
            del _session_services[session_id]
