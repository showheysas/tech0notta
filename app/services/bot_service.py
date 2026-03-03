"""
Bot派遣サービス
Azure Container Apps (ACA) Job を使って会議Botコンテナを起動・管理する
"""
import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
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
    container_id: Optional[str] = None       # ACA Job execution name
    error_message: Optional[str] = None
    platform: BotPlatform = BotPlatform.ZOOM
    meeting_url: Optional[str] = None

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
    """Bot派遣サービス（ACA Job 方式）"""

    def __init__(self):
        # インメモリでセッション管理
        self._sessions: Dict[str, BotSession] = {}
        self._aca_client = None

    def _get_aca_client(self):
        """Azure Container Apps API クライアントを取得（遅延初期化）"""
        if self._aca_client is None:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.containerapp import ContainerAppsAPIClient
            from app.config import settings

            credential = DefaultAzureCredential()
            self._aca_client = ContainerAppsAPIClient(
                credential=credential,
                subscription_id=settings.AZURE_SUBSCRIPTION_ID,
            )
        return self._aca_client

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
        Botを会議に派遣（ACA Job execution を開始）

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

        # ACA Job execution を起動（非同期）
        asyncio.create_task(self._run_aca_job(session))

        return session

    async def _run_aca_job(self, session: BotSession) -> None:
        """
        ACA Job execution を開始して会議Botコンテナを起動する。
        コンテナには Xvfb, PulseAudio, Chromium が全てプリインストール済み。
        """
        try:
            session.status = BotStatus.JOINING
            session.updated_at = datetime.utcnow()

            logger.info(
                f"🚀 ACA Job起動開始: session_id={session.id}, "
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

            # ACA Job execution の環境変数
            from azure.mgmt.containerapp.models import (
                JobExecutionTemplate,
                JobExecutionContainer,
                ContainerResources,
            )

            env_vars = [
                {"name": "PLATFORM", "value": session.platform.value},
                {"name": "MEETING_URL", "value": session.meeting_url or session.meeting_id},
                {"name": "MEETING_ID", "value": session.meeting_id},
                {"name": "BOT_NAME", "value": bot_name},
                {"name": "BACKEND_URL", "value": settings.BACKEND_URL},
                {"name": "SESSION_ID", "value": session.id},
                {"name": "AZURE_SPEECH_REGION", "value": settings.AZURE_SPEECH_REGION or "japaneast"},
            ]

            # AZURE_SPEECH_KEY は ACA Job の secret として設定済み（secretRef で参照）
            env_vars.append({"name": "AZURE_SPEECH_KEY", "secretRef": "azure-speech-key"})

            template = JobExecutionTemplate(
                containers=[
                    JobExecutionContainer(
                        name="bot",
                        image=settings.ACA_BOT_IMAGE,
                        env=env_vars,
                        resources=ContainerResources(cpu=1.0, memory="2Gi"),
                    )
                ],
            )

            # Azure SDK は同期的なので run_in_executor で非同期化
            client = self._get_aca_client()
            loop = asyncio.get_event_loop()

            execution = await loop.run_in_executor(
                None,
                lambda: client.jobs.begin_start(
                    resource_group_name=settings.AZURE_RESOURCE_GROUP,
                    job_name=settings.ACA_BOT_JOB_NAME,
                    template=template,
                ).result()
            )

            session.container_id = execution.name
            session.status = BotStatus.IN_MEETING
            session.updated_at = datetime.utcnow()

            logger.info(
                f"✅ ACA Job execution 開始: execution_name={execution.name}, "
                f"session_id={session.id}"
            )

        except Exception as e:
            logger.error(f"ACA Job起動エラー: {e}")
            session.status = BotStatus.ERROR
            session.error_message = str(e)
            session.updated_at = datetime.utcnow()

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
        Botを会議から退出させる（ACA Job execution を停止）

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

        # ACA Job execution を停止
        if session.container_id:
            try:
                from app.config import settings
                client = self._get_aca_client()
                loop = asyncio.get_event_loop()

                await loop.run_in_executor(
                    None,
                    lambda: client.jobs.begin_stop_execution(
                        resource_group_name=settings.AZURE_RESOURCE_GROUP,
                        job_name=settings.ACA_BOT_JOB_NAME,
                        job_execution_name=session.container_id,
                    ).result()
                )
                logger.info(f"ACA execution 停止完了: {session.container_id}")
            except Exception as e:
                logger.error(f"ACA execution 停止エラー: {e}")

        session.status = BotStatus.COMPLETED
        session.updated_at = datetime.utcnow()

        logger.info(f"✅ Bot退出完了: session_id={session_id}")
        return True

    async def get_bot_logs(self, session_id: str) -> str:
        """ACA execution の情報を返す"""
        session = self._sessions.get(session_id)
        if not session:
            return "セッションが見つかりません"
        return (
            f"ACA execution: {session.container_id or '未起動'}, "
            f"ステータス: {session.status.value}"
        )

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
