#!/usr/bin/env python3
"""
Bot HTTP Server - ACA App (minReplicas=1) 用
常時起動コンテナ内で HTTP リクエストを待ち受け、会議参加を即座に実行する。

エンドポイント:
  POST /dispatch  - 会議に参加
  GET  /health    - ヘルスチェック
  GET  /status    - 現在の状態 (idle/busy)
"""
import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# スクリプトパス解決
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(_SCRIPT_DIR, "realtime_transcriber.py")):
    _BOT_RUNNER_DIR = _SCRIPT_DIR
else:
    _BOT_RUNNER_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "bot_runner")

REALTIME_TRANSCRIBER = os.path.join(_BOT_RUNNER_DIR, "realtime_transcriber.py")
AUDIO_CAPTURE = os.path.join(_BOT_RUNNER_DIR, "audio_capture.sh")
UPLOAD_WORKFLOW = os.path.join(_BOT_RUNNER_DIR, "upload_workflow.py")


class BotState:
    """Bot の状態管理（1 コンテナ = 1 会議）"""

    def __init__(self):
        self.busy = False
        self.session_id: str | None = None
        self.lock = threading.Lock()

    def acquire(self, session_id: str) -> bool:
        with self.lock:
            if self.busy:
                return False
            self.busy = True
            self.session_id = session_id
            return True

    def release(self):
        with self.lock:
            self.busy = False
            self.session_id = None


state = BotState()


def run_bot(platform: str, meeting_url: str, bot_name: str, session_id: str, backend_url: str):
    """Bot を実行し、完了後に状態をリリースする"""
    transcriber_process = None
    audio_capture_process = None
    error_message = None

    try:
        # リアルタイム文字起こし開始
        speech_key = os.environ.get("AZURE_SPEECH_KEY")
        speech_region = os.environ.get("AZURE_SPEECH_REGION", "japaneast")
        if speech_key:
            env = os.environ.copy()
            env["SESSION_ID"] = session_id
            env["BACKEND_URL"] = backend_url
            env["AZURE_SPEECH_KEY"] = speech_key
            env["AZURE_SPEECH_REGION"] = speech_region
            transcriber_process = subprocess.Popen(
                [sys.executable, REALTIME_TRANSCRIBER],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            def log_transcriber():
                for line in iter(transcriber_process.stdout.readline, b""):
                    logger.info(f"[TRANSCRIBER] {line.decode().rstrip()}")

            threading.Thread(target=log_transcriber, daemon=True).start()

        # 音声キャプチャ開始
        audio_capture_process = subprocess.Popen(
            [AUDIO_CAPTURE], stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

        def log_capture():
            if audio_capture_process.stdout:
                for line in iter(audio_capture_process.stdout.readline, b""):
                    logger.info(f"[CAPTURE] {line.decode().rstrip()}")

        threading.Thread(target=log_capture, daemon=True).start()

        # Bot 起動
        if platform == "google_meet":
            from google_meet_bot import GoogleMeetBot
            GoogleMeetBot(meeting_url=meeting_url, bot_name=bot_name).run()
        elif platform == "teams":
            from teams_bot import TeamsBot
            TeamsBot(meeting_url=meeting_url, bot_name=bot_name).run()
        elif platform == "zoom":
            from zoom_bot import ZoomBot
            ZoomBot(meeting_url=meeting_url, bot_name=bot_name).run()
        else:
            raise ValueError(f"未対応のプラットフォーム: {platform}")

    except Exception as e:
        import traceback
        error_message = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        logger.error(f"Bot実行エラー: {error_message}")
    finally:
        # App Service に会議終了を通知
        try:
            import httpx
            payload = {"error_message": error_message} if error_message else {}
            httpx.post(f"{backend_url}/api/bot/{session_id}/complete", json=payload, timeout=10.0)
        except Exception as e:
            logger.warning(f"会議終了通知失敗: {e}")

        # プロセスクリーンアップ
        for proc, name in [(transcriber_process, "transcriber"), (audio_capture_process, "audio_capture")]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

        # アップロードワークフロー実行
        try:
            subprocess.run([sys.executable, UPLOAD_WORKFLOW], capture_output=True, text=True)
        except Exception as e:
            logger.error(f"ワークフロー実行エラー: {e}")

        # 状態をリリース（次の会議を受付可能に）
        state.release()
        logger.info(f"Bot 完了、待機状態に復帰: session_id={session_id}")


class BotHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "healthy"})
        elif self.path == "/status":
            self._respond(200, {"busy": state.busy, "session_id": state.session_id})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/dispatch":
            self._respond(404, {"error": "not found"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

        platform = body.get("platform", "google_meet")
        meeting_url = body.get("meeting_url", "")
        bot_name = body.get("bot_name", "Tech Bot")
        session_id = body.get("session_id", str(uuid.uuid4()))
        backend_url = body.get("backend_url", os.environ.get("BACKEND_URL", "http://localhost:8000"))

        if not meeting_url:
            self._respond(400, {"error": "meeting_url is required"})
            return

        if not state.acquire(session_id):
            self._respond(409, {"error": "busy", "current_session_id": state.session_id})
            return

        # Bot をバックグラウンドスレッドで実行（即座にレスポンスを返す）
        threading.Thread(
            target=run_bot,
            args=(platform, meeting_url, bot_name, session_id, backend_url),
            daemon=True,
        ).start()

        logger.info(f"Bot dispatch 受付: session_id={session_id}, platform={platform}")
        self._respond(200, {"success": True, "session_id": session_id})

    def _respond(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        # デフォルトのアクセスログを抑制（health check がうるさい）
        pass


def main():
    port = int(os.environ.get("BOT_SERVER_PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), BotHandler)
    logger.info(f"Bot HTTP Server 起動: port={port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
