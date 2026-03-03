#!/usr/bin/env python3
"""
Browser Bot エントリポイント
Google Meet / Microsoft Teams にゲスト参加するBotのオーケストレーター
"""
import os
import sys
import subprocess
import logging
import threading
import time
import uuid

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# スクリプトパス解決: bot_runner/ にある共有スクリプトを参照
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))        # browser_bot/
_BOT_RUNNER_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "bot_runner")  # bot_runner/
SETUP_PULSEAUDIO = os.path.join(_BOT_RUNNER_DIR, "setup-pulseaudio.sh")
REALTIME_TRANSCRIBER = os.path.join(_BOT_RUNNER_DIR, "realtime_transcriber.py")
AUDIO_CAPTURE = os.path.join(_BOT_RUNNER_DIR, "audio_capture.sh")
UPLOAD_WORKFLOW = os.path.join(_BOT_RUNNER_DIR, "upload_workflow.py")


def start_realtime_transcription(session_id: str) -> subprocess.Popen | None:
    """リアルタイム文字起こしプロセスを起動"""
    backend_url = os.environ.get('BACKEND_URL', 'http://host.docker.internal:8000')
    speech_key = os.environ.get('AZURE_SPEECH_KEY')
    speech_region = os.environ.get('AZURE_SPEECH_REGION', 'japaneast')

    if not speech_key:
        logger.warning("⚠️ AZURE_SPEECH_KEY が設定されていないため、リアルタイム文字起こしをスキップ")
        return None

    logger.info("🎙️ リアルタイム文字起こしを開始...")

    env = os.environ.copy()
    env['SESSION_ID'] = session_id
    env['BACKEND_URL'] = backend_url
    env['AZURE_SPEECH_KEY'] = speech_key
    env['AZURE_SPEECH_REGION'] = speech_region

    process = subprocess.Popen(
        [sys.executable, REALTIME_TRANSCRIBER],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )

    def log_output():
        for line in iter(process.stdout.readline, b''):
            logger.info(f"[TRANSCRIBER] {line.decode().rstrip()}")

    threading.Thread(target=log_output, daemon=True).start()
    return process


def main():
    logger.info("🤖 Tech Notta Browser Bot 起動")

    platform = os.environ.get('PLATFORM', 'google_meet')
    meeting_url = os.environ.get('MEETING_URL', '')
    meeting_id = os.environ.get('MEETING_ID', meeting_url)
    bot_name = os.environ.get('BOT_NAME', 'Tech Bot')
    session_id = os.environ.get('SESSION_ID', '')

    if not meeting_url:
        logger.error("❌ MEETING_URL が設定されていません")
        sys.exit(1)

    if not session_id:
        session_id = str(uuid.uuid4())
        os.environ['SESSION_ID'] = session_id

    logger.info(
        f"📋 設定: platform={platform}, meeting_url={meeting_url}, "
        f"bot_name={bot_name}, session_id={session_id}"
    )

    # PulseAudio設定は bot_service.py が subprocess 起動前に実施済み
    # ここで再度 setup-pulseaudio.sh を実行すると module-null-sink が二重ロードされるためスキップ
    logger.info("🔊 PulseAudio設定: bot_service.py で設定済み（スキップ）")

    # リアルタイム文字起こし開始
    transcriber_process = start_realtime_transcription(session_id)

    # 音声キャプチャ開始
    logger.info("🎙️ 音声キャプチャを開始...")
    audio_capture_process = subprocess.Popen(
        [AUDIO_CAPTURE],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )

    def log_capture_output():
        if audio_capture_process.stdout:
            for line in iter(audio_capture_process.stdout.readline, b''):
                logger.info(f"[CAPTURE] {line.decode().rstrip()}")

    threading.Thread(target=log_capture_output, daemon=True).start()

    backend_url = os.environ.get('BACKEND_URL', 'http://host.docker.internal:8000')

    try:
        if platform == 'google_meet':
            from google_meet_bot import GoogleMeetBot
            logger.info(f"🟢 Google Meet Bot 起動: {meeting_url}")
            GoogleMeetBot(meeting_url=meeting_url, bot_name=bot_name).run()
        elif platform == 'teams':
            from teams_bot import TeamsBot
            logger.info(f"🟣 Teams Bot 起動: {meeting_url}")
            TeamsBot(meeting_url=meeting_url, bot_name=bot_name).run()
        elif platform == 'zoom':
            from zoom_bot import ZoomBot
            logger.info(f"🔵 Zoom Bot 起動: {meeting_url}")
            ZoomBot(meeting_url=meeting_url, bot_name=bot_name).run()
        else:
            logger.error(f"❌ 未対応のプラットフォーム: {platform}")
            sys.exit(1)
    finally:
        logger.info("🛑 クリーンアップ開始...")

        # App Service に会議終了を通知（フロントエンドのステータスポーリングが自動終了フローを開始する）
        try:
            import httpx
            httpx.post(f"{backend_url}/api/bot/{session_id}/complete", timeout=10.0)
            logger.info("✅ App Service に会議終了を通知しました")
        except Exception as e:
            logger.warning(f"会議終了通知失敗（処理は継続）: {e}")

        if transcriber_process and transcriber_process.poll() is None:
            logger.info("  realtime_transcriber.py を停止中...")
            transcriber_process.terminate()
            try:
                transcriber_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                transcriber_process.kill()

        if audio_capture_process and audio_capture_process.poll() is None:
            logger.info("  audio_capture.sh を停止中...")
            audio_capture_process.terminate()
            try:
                audio_capture_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                audio_capture_process.kill()

        logger.info("📤 自動アップロード & 議事録作成ワークフローを実行...")
        try:
            workflow_result = subprocess.run(
                [sys.executable, UPLOAD_WORKFLOW],
                capture_output=True,
                text=True
            )
            if workflow_result.returncode == 0:
                logger.info("✅ ワークフロー正常終了")
                logger.info(workflow_result.stdout)
            else:
                logger.error(f"⚠️ ワークフロー失敗 (code: {workflow_result.returncode})")
                logger.error(workflow_result.stderr)
        except Exception as e:
            logger.error(f"ワークフロー実行エラー: {e}")


if __name__ == "__main__":
    main()
