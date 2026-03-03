"""
Bot派遣サービス
Zoom / Google Meet / Microsoft Teams へのBot派遣を管理する
"""
import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from app.zoom_config import zoom_config

logger = logging.getLogger(__name__)


class BotStatus(str, Enum):
    """Botの状態"""
    PENDING = "pending"          # 起動準備中
    JOINING = "joining"          # 会議に参加中
    IN_MEETING = "in_meeting"    # 会議参加中
    RECORDING = "recording"      # 録音中
    LEAVING = "leaving"          # 退出中
    COMPLETED = "completed"      # 完了
    ERROR = "error"              # エラー


class BotPlatform(str, Enum):
    """Botが参加する会議プラットフォーム"""
    ZOOM = "zoom"
    GOOGLE_MEET = "google_meet"
    TEAMS = "teams"


@dataclass
class BotSession:
    """Bot派遣セッション"""
    id: str
    meeting_id: str
    meeting_password: Optional[str]
    status: BotStatus
    created_at: datetime
    updated_at: datetime
    container_id: Optional[str] = None
    error_message: Optional[str] = None
    platform: BotPlatform = BotPlatform.ZOOM
    meeting_url: Optional[str] = None
    process: Optional[Any] = None       # asyncio.subprocess.Process (bot)
    xvfb_process: Optional[Any] = None  # asyncio.subprocess.Process (Xvfb)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "meeting_id": self.meeting_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "container_id": self.container_id,
            "error_message": self.error_message,
            "platform": self.platform.value,
            "meeting_url": self.meeting_url,
        }


class BotService:
    """Bot派遣サービス"""

    def __init__(self):
        # インメモリでセッション管理（本番ではDBに保存）
        self._sessions: Dict[str, BotSession] = {}
        # Xvfb ディスプレイ番号スロット管理（同時複数Bot対応）
        self._slots: Dict[int, str] = {}  # slot_index → session_id

    def _allocate_slot(self, session_id: str) -> int:
        """ユニークな Xvfb ディスプレイスロットを確保して返す"""
        for i in range(10):
            if i not in self._slots:
                self._slots[i] = session_id
                return i
        raise RuntimeError("同時起動可能なBot数の上限（10）に達しました")

    def _release_slot(self, session_id: str) -> None:
        """スロットを解放する"""
        for slot, sid in list(self._slots.items()):
            if sid == session_id:
                del self._slots[slot]
                return

    def _parse_meeting_url(self, url_or_id: str) -> tuple[str, Optional[str]]:
        """
        ミーティングURLまたはIDから、会議番号とパスワードを抽出

        Returns:
            (meeting_id, password)
        """
        import re
        from urllib.parse import urlparse, parse_qs

        meeting_id = ""
        password = None

        # URLかどうか判定
        if "zoom.us" in url_or_id:
            # URLからID抽出
            match = re.search(r'/j/(\d+)', url_or_id)
            if match:
                meeting_id = match.group(1)

            # URLからパスワード抽出
            parsed = urlparse(url_or_id)
            query = parse_qs(parsed.query)
            if 'pwd' in query:
                password = query['pwd'][0]
        else:
            # 数字のみの場合はIDとして扱う
            meeting_id = ''.join(filter(str.isdigit, url_or_id))

        return meeting_id, password

    def _extract_meeting_id(self, meeting_url_or_id: str) -> str:
        # 後方互換性のため残すが、内部では _parse_meeting_url を使う
        mid, _ = self._parse_meeting_url(meeting_url_or_id)
        return mid

    def _detect_platform(self, url: str) -> BotPlatform:
        """URLからプラットフォームを自動判定"""
        if "meet.google.com" in url:
            return BotPlatform.GOOGLE_MEET
        if "teams.microsoft.com" in url or "teams.live.com" in url:
            return BotPlatform.TEAMS
        return BotPlatform.ZOOM  # zoom.us / 数字IDはZoom

    async def dispatch_bot(
        self,
        meeting_id: str,
        password: Optional[str] = None,
        meeting_url: Optional[str] = None,
        platform: Optional[BotPlatform] = None,
    ) -> BotSession:
        """
        Botを会議に派遣

        Args:
            meeting_id: 会議ID（URLでも可）
            password: 会議パスワード（Zoomのみ）
            meeting_url: 会議URL（Google Meet / Teams で必須）
            platform: プラットフォーム（省略時は自動判定）

        Returns:
            BotSession
        """
        # プラットフォーム自動判定
        if platform is None:
            platform = self._detect_platform(meeting_url or meeting_id)

        # Zoom / Google Meet / Teams すべてブラウザBot経由でURLをそのまま使用
        clean_meeting_id = meeting_url or meeting_id

        if not clean_meeting_id:
            raise ValueError("有効な会議URLを指定してください")

        # セッション作成
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()

        session = BotSession(
            id=session_id,
            meeting_id=clean_meeting_id,
            meeting_password=None,
            status=BotStatus.PENDING,
            created_at=now,
            updated_at=now,
            platform=platform,
            meeting_url=meeting_url,
        )
        self._sessions[session_id] = session

        logger.info(
            f"🤖 Bot派遣セッション作成: "
            f"session_id={session_id}, meeting_id={clean_meeting_id}, "
            f"platform={platform.value}"
        )

        # Bot Runnerを起動（非同期）
        asyncio.create_task(self._run_browser_bot(session))

        return session

    async def _run_browser_bot(self, session: BotSession) -> None:
        """
        ブラウザBotを App Service 内の subprocess として起動して会議に参加。
        ACI コールドスタート（60〜90秒）を排除し、1〜3秒で参加開始できる。
        """
        try:
            session.status = BotStatus.JOINING
            session.updated_at = datetime.utcnow()

            logger.info(
                f"🚀 ブラウザBot起動開始: session_id={session.id}, "
                f"platform={session.platform.value}, meeting_url={session.meeting_url}"
            )

            # ライブ文字起こしサービスにセッションを作成
            from app.services.live_transcription_service import live_transcription_service
            live_transcription_service.create_session(
                session_id=session.id,
                meeting_id=session.meeting_id,
                meeting_topic=f"会議 {session.meeting_id}"
            )

            from app.config import settings
            from app.google_meet_config import google_meet_config
            from app.teams_config import teams_config

            if session.platform == BotPlatform.GOOGLE_MEET:
                bot_name = google_meet_config.bot_display_name
            elif session.platform == BotPlatform.ZOOM:
                bot_name = zoom_config.bot_display_name
            else:
                bot_name = teams_config.bot_display_name

            # スロット割り当て（Bot ごとにユニークな Xvfb display 番号を確保）
            slot = self._allocate_slot(session.id)
            display_num = 99 + slot
            pulse_path = f"/tmp/pulse-{session.id}"
            os.makedirs(pulse_path, exist_ok=True)

            env = dict(os.environ)
            env.update({
                "DISPLAY": f":{display_num}",
                "PULSE_RUNTIME_PATH": pulse_path,
                "PULSE_SERVER": f"unix:{pulse_path}/native",
                "PLATFORM": session.platform.value,
                "MEETING_URL": session.meeting_url or session.meeting_id,
                "MEETING_ID": session.meeting_id,
                "BOT_NAME": bot_name,
                "BACKEND_URL": settings.BACKEND_URL,
                "SESSION_ID": session.id,
                "AZURE_SPEECH_KEY": settings.AZURE_SPEECH_KEY or "",
                "AZURE_SPEECH_REGION": settings.AZURE_SPEECH_REGION or "japaneast",
            })

            # Xvfb 起動前にロックファイルをクリーンアップ（App Service 再起動後の残留ロック対策）
            for stale in [f"/tmp/.X{display_num}-lock", f"/tmp/.X11-unix/X{display_num}"]:
                try:
                    os.remove(stale)
                except FileNotFoundError:
                    pass

            # Xvfb 起動（仮想ディスプレイ）
            xvfb = await asyncio.create_subprocess_exec(
                "Xvfb", f":{display_num}", "-screen", "0", "1280x720x24",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.sleep(1)  # Xvfb の初期化を待つ

            # ブラウザBot プロセス起動
            # __file__ から相対パスで entrypoint.py を特定（/app シンボリックリンクに依存しない）
            _this_dir = os.path.dirname(os.path.abspath(__file__))          # app/services/
            _app_dir = os.path.dirname(_this_dir)                           # app/
            entrypoint_path = os.path.join(_app_dir, "browser_bot", "entrypoint.py")
            logger.info(f"entrypoint_path={entrypoint_path}")

            process = await asyncio.create_subprocess_exec(
                "python3", entrypoint_path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            session.process = process
            session.xvfb_process = xvfb
            session.status = BotStatus.IN_MEETING
            session.updated_at = datetime.utcnow()

            logger.info(
                f"✅ ブラウザBot参加完了 (PID: {process.pid}): session_id={session.id}"
            )

            # subprocess の出力をログに転送（バッファ詰まり防止）
            asyncio.create_task(self._log_subprocess_output(session))
            # subprocess の終了を監視してステータスを更新
            asyncio.create_task(self._monitor_process(session))

        except Exception as e:
            logger.error(f"ブラウザBot起動エラー: {e}")
            session.status = BotStatus.ERROR
            session.error_message = str(e)
            session.updated_at = datetime.utcnow()
            self._release_slot(session.id)

    async def _log_subprocess_output(self, session: BotSession) -> None:
        """subprocess の stdout をロガーに転送する（パイプバッファ詰まり防止）"""
        if not session.process or not session.process.stdout:
            return
        async for line in session.process.stdout:
            logger.info(f"[Bot {session.id[:8]}] {line.decode().rstrip()}")

    async def _monitor_process(self, session: BotSession) -> None:
        """ブラウザBotプロセスの終了を監視し、ステータスを更新する"""
        if not session.process:
            return
        returncode = await session.process.wait()
        logger.info(
            f"ブラウザBotプロセス終了: session_id={session.id}, returncode={returncode}"
        )
        if session.status not in (BotStatus.COMPLETED, BotStatus.ERROR, BotStatus.LEAVING):
            if returncode == 0:
                session.status = BotStatus.COMPLETED
            else:
                session.status = BotStatus.ERROR
                session.error_message = f"プロセス終了コード: {returncode}"
            session.updated_at = datetime.utcnow()
        self._release_slot(session.id)

    def get_session(self, session_id: str) -> Optional[BotSession]:
        """セッション取得"""
        return self._sessions.get(session_id)

    def get_sessions_by_meeting(self, meeting_id: str) -> list[BotSession]:
        """会議IDでセッション検索"""
        clean_id = self._extract_meeting_id(meeting_id)
        return [
            s for s in self._sessions.values()
            if s.meeting_id == clean_id
        ]

    def get_active_sessions(self) -> list[BotSession]:
        """
        アクティブなセッション一覧を取得
        （終了・エラー以外のセッション）
        """
        return [
            s for s in self._sessions.values()
            if s.status not in (BotStatus.COMPLETED, BotStatus.ERROR)
        ]

    async def terminate_bot(self, session_id: str) -> bool:
        """
        Botを会議から退出させる（subprocess を終了）

        Args:
            session_id: セッションID

        Returns:
            成功時True
        """
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"セッションが見つかりません: {session_id}")
            return False

        session.status = BotStatus.LEAVING
        session.updated_at = datetime.utcnow()

        logger.info(f"🛑 Bot退出開始: session_id={session_id}")

        # ブラウザBot プロセス終了
        if session.process and session.process.returncode is None:
            try:
                session.process.terminate()
                await asyncio.wait_for(session.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                session.process.kill()
            except Exception as e:
                logger.error(f"ブラウザBotプロセス終了エラー: {e}")

        # Xvfb プロセス終了
        if session.xvfb_process and session.xvfb_process.returncode is None:
            try:
                session.xvfb_process.terminate()
            except Exception as e:
                logger.error(f"Xvfbプロセス終了エラー: {e}")

        self._release_slot(session_id)

        session.status = BotStatus.COMPLETED
        session.updated_at = datetime.utcnow()

        logger.info(f"✅ Bot退出完了: session_id={session_id}")
        return True

    async def get_bot_logs(self, session_id: str) -> str:
        """プロセスの状態を返す（subprocess方式ではリアルタイムログはロガーに出力済み）"""
        session = self._sessions.get(session_id)
        if not session:
            return "セッションが見つかりません"
        if not session.process:
            return "プロセスが起動していません"
        return f"プロセスPID: {session.process.pid}, ステータス: {session.status.value}"

    async def terminate_sessions_by_meeting_id(self, meeting_id: str) -> int:
        """
        会議IDに関連するアクティブなBotセッションを全て終了する

        Args:
            meeting_id: 会議ID

        Returns:
            終了させたセッション数
        """
        sessions = self.get_sessions_by_meeting(meeting_id)
        count = 0
        for session in sessions:
            # 完了・エラー済みでなければ終了処理を実行
            if session.status not in (BotStatus.COMPLETED, BotStatus.ERROR):
                await self.terminate_bot(session.id)
                count += 1
        return count


# シングルトンインスタンス
bot_service = BotService()
