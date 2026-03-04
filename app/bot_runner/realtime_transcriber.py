#!/usr/bin/env python3
"""
リアルタイム文字起こしモジュール（話者分離対応版）
PulseAudioから音声を取得し、Azure Conversation Transcription で継続認識を行い、
バックエンドにセグメントを送信する
"""
import os
import sys
import time
import logging
import threading
import queue
from datetime import datetime, timezone, timedelta
from typing import Optional

# JST (UTC+9) タイムゾーン
JST = timezone(timedelta(hours=9))

try:
    import azure.cognitiveservices.speech as speechsdk
except ImportError:
    speechsdk = None
    print("WARNING: azure-cognitiveservices-speech not installed. Real-time transcription disabled.")

import httpx

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RealtimeTranscriber:
    """
    Azure Conversation Transcription を使ったリアルタイム話者分離付き文字起こし
    """
    
    def __init__(
        self,
        session_id: str,
        backend_url: str,
        speech_key: str,
        speech_region: str,
        language: str = "ja-JP"
    ):
        self.session_id = session_id
        self.backend_url = backend_url
        self.speech_key = speech_key
        self.speech_region = speech_region
        self.language = language
        
        self._running = False
        self._transcriber: Optional[speechsdk.transcription.ConversationTranscriber] = None
        self._segment_queue: queue.Queue = queue.Queue()
        self._sender_thread: Optional[threading.Thread] = None
        
        # 話者トラッキング（speaker_id -> 表示名）
        self._speaker_map: dict[str, str] = {}
        self._speaker_counter = 0
    
    def _get_speaker_label(self, speaker_id: str) -> str:
        """
        speaker_id を見やすいラベルに変換（話者1, 話者2, ...）
        """
        if not speaker_id or speaker_id == "Unknown":
            return "参加者"
        
        if speaker_id not in self._speaker_map:
            self._speaker_counter += 1
            self._speaker_map[speaker_id] = f"話者{self._speaker_counter}"
            logger.info(f"🎤 新しい話者検出: {speaker_id} -> {self._speaker_map[speaker_id]}")
        
        return self._speaker_map[speaker_id]
    
    def start(self) -> None:
        """
        リアルタイム文字起こしを開始（話者分離付き）
        """
        if speechsdk is None:
            logger.error("Azure Speech SDK がインストールされていません")
            return
        
        logger.info(f"🎙️ リアルタイム文字起こし開始（話者分離モード）: session_id={self.session_id}")
        
        # セッション初期化
        self._init_session()
        
        # Speech Config
        speech_config = speechsdk.SpeechConfig(
            subscription=self.speech_key,
            region=self.speech_region
        )
        speech_config.speech_recognition_language = self.language
        
        # 話者分離を有効化
        speech_config.set_property(
            speechsdk.PropertyId.SpeechServiceConnection_LanguageIdMode,
            "Continuous"
        )
        
        # PulseAudio のデフォルト入力デバイスから音声を取得
        audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
        
        # ConversationTranscriber を使用（話者分離対応）
        self._transcriber = speechsdk.transcription.ConversationTranscriber(
            speech_config=speech_config,
            audio_config=audio_config
        )
        
        # イベントハンドラ設定
        self._transcriber.transcribed.connect(self._on_transcribed)
        self._transcriber.transcribing.connect(self._on_transcribing)
        self._transcriber.session_stopped.connect(self._on_session_stopped)
        self._transcriber.canceled.connect(self._on_canceled)
        
        # セグメント送信スレッド開始
        self._running = True
        self._sender_thread = threading.Thread(target=self._segment_sender_loop, daemon=True)
        self._sender_thread.start()
        
        # 継続認識開始
        self._transcriber.start_transcribing_async()
        logger.info("✅ 話者分離付き継続認識開始")
    
    def stop(self) -> None:
        """
        リアルタイム文字起こしを停止
        """
        logger.info("🛑 リアルタイム文字起こし停止")
        
        self._running = False
        
        if self._transcriber:
            self._transcriber.stop_transcribing_async()
            self._transcriber = None
        
        if self._sender_thread and self._sender_thread.is_alive():
            self._sender_thread.join(timeout=5)
    
    def _init_session(self) -> None:
        """
        バックエンドでセッションを初期化
        """
        try:
            meeting_id = os.environ.get('MEETING_NUMBER', 'unknown')
            response = httpx.post(
                f"{self.backend_url}/api/live/segments/{self.session_id}/init",
                params={
                    "meeting_id": meeting_id,
                    "meeting_topic": f"会議 {meeting_id}"
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"✅ セッション初期化完了: {response.json()}")
        except Exception as e:
            logger.error(f"セッション初期化失敗: {e}")
    
    def _on_transcribed(self, evt: speechsdk.transcription.ConversationTranscriptionEventArgs) -> None:
        """
        認識完了イベント（確定テキスト + 話者ID）
        """
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = evt.result.text.strip()
            speaker_id = evt.result.speaker_id if hasattr(evt.result, 'speaker_id') else "Unknown"
            
            if text:
                speaker_label = self._get_speaker_label(speaker_id)
                logger.info(f"📝 認識完了 [{speaker_label}]: {text}")
                
                self._segment_queue.put({
                    "speaker": speaker_label,
                    "speaker_id": speaker_id,  # 元のIDも保存（マッピング用）
                    "text": text,
                    "time": datetime.now(JST).strftime("%H:%M")
                })
    
    def _on_transcribing(self, evt: speechsdk.transcription.ConversationTranscriptionEventArgs) -> None:
        """
        認識中イベント（中間結果）
        """
        if evt.result.text:
            logger.debug(f"🔄 認識中: {evt.result.text}")
    
    def _on_session_stopped(self, evt: speechsdk.SessionEventArgs) -> None:
        """
        セッション終了イベント
        """
        logger.info("🔚 認識セッション終了")
    
    def _on_canceled(self, evt: speechsdk.transcription.ConversationTranscriptionCanceledEventArgs) -> None:
        """
        キャンセルイベント（エラー含む）
        """
        if evt.reason == speechsdk.CancellationReason.Error:
            logger.error(f"❌ 認識エラー: {evt.error_details}")
        else:
            logger.info(f"⚠️ 認識キャンセル: {evt.reason}")
    
    def _segment_sender_loop(self) -> None:
        """
        セグメント送信ループ（別スレッド）
        """
        logger.info("📤 セグメント送信スレッド開始")
        
        while self._running:
            try:
                # キューからセグメントを取得（タイムアウト付き）
                segment = self._segment_queue.get(timeout=1)
                self._send_segment(segment)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"セグメント送信エラー: {e}")
        
        logger.info("📤 セグメント送信スレッド終了")
    
    def _send_segment(self, segment: dict) -> None:
        """
        セグメントをバックエンドに送信
        """
        try:
            response = httpx.post(
                f"{self.backend_url}/api/live/segments/{self.session_id}/push",
                json=segment,
                timeout=10
            )
            response.raise_for_status()
            logger.debug(f"✅ セグメント送信完了: {segment['text'][:30]}...")
        except Exception as e:
            logger.error(f"セグメント送信失敗: {e}")


def main():
    """
    メイン処理
    """
    logger.info("========================================")
    logger.info("  🎙️ リアルタイム文字起こしサービス")
    logger.info("  🎤 話者分離モード (Azure Conversation Transcription)")
    logger.info("========================================")
    
    # 環境変数から設定を取得
    session_id = os.environ.get('SESSION_ID')
    backend_url = os.environ.get('BACKEND_URL', 'http://host.docker.internal:8000')
    speech_key = os.environ.get('AZURE_SPEECH_KEY')
    speech_region = os.environ.get('AZURE_SPEECH_REGION', 'japaneast')
    
    if not session_id:
        logger.error("❌ SESSION_ID が設定されていません")
        sys.exit(1)
    
    if not speech_key:
        logger.error("❌ AZURE_SPEECH_KEY が設定されていません")
        sys.exit(1)
    
    logger.info(f"  Session ID: {session_id}")
    logger.info(f"  Backend URL: {backend_url}")
    logger.info(f"  Speech Region: {speech_region}")
    logger.info("")
    
    transcriber = RealtimeTranscriber(
        session_id=session_id,
        backend_url=backend_url,
        speech_key=speech_key,
        speech_region=speech_region
    )
    
    try:
        transcriber.start()
        
        # 無限ループで待機（Ctrl+C または会議終了まで）
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("⚠️ 中断シグナル受信")
    finally:
        transcriber.stop()


if __name__ == "__main__":
    main()
