"""
Bot派遣サービス
Zoom / Google Meet / Microsoft Teams へのBot派遣を管理する
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from app.zoom_config import zoom_config
from app.services.sdk_jwt_service import sdk_jwt_service

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

    def _get_aci_client(self):
        """ACI クライアントを返す（DefaultAzureCredential で Managed Identity 対応）"""
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.containerinstance import ContainerInstanceManagementClient
        from app.config import settings

        credential = DefaultAzureCredential()
        return ContainerInstanceManagementClient(credential, settings.AZURE_SUBSCRIPTION_ID)

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

        if platform == BotPlatform.ZOOM:
            # Zoom: URLからID/パスワードを抽出
            clean_meeting_id, extracted_password = self._parse_meeting_url(meeting_id)
            final_password = password or extracted_password

            if not clean_meeting_id:
                raise ValueError("有効なZoom会議IDまたはURLを指定してください")

            if not sdk_jwt_service.is_configured():
                raise ValueError(
                    "SDK設定が不完全です。"
                    "ZOOM_SDK_KEY, ZOOM_SDK_SECRETを設定してください。"
                )

            jwt_token = sdk_jwt_service.generate_jwt(
                meeting_number=clean_meeting_id,
                role=0  # 参加者として参加
            )
            if not jwt_token:
                raise ValueError("SDK JWT生成に失敗しました")
        else:
            # Google Meet / Teams: URLをそのまま使用
            clean_meeting_id = meeting_url or meeting_id
            final_password = None
            jwt_token = None

            if not clean_meeting_id:
                raise ValueError("有効な会議URLを指定してください")

        # セッション作成
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()

        session = BotSession(
            id=session_id,
            meeting_id=clean_meeting_id,
            meeting_password=final_password,
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
        asyncio.create_task(self._run_bot(session, jwt_token))

        return session

    async def _run_bot(self, session: BotSession, jwt_token: Optional[str]) -> None:
        """プラットフォームに応じてBot Runnerコンテナを起動"""
        if session.platform == BotPlatform.ZOOM:
            await self._run_zoom_bot(session, jwt_token)
        else:
            await self._run_browser_bot(session)

    async def _run_zoom_bot(self, session: BotSession, jwt_token: Optional[str]) -> None:
        """
        Zoom Bot Runner を ACI コンテナグループとして起動して会議に参加
        """
        try:
            session.status = BotStatus.JOINING
            session.updated_at = datetime.utcnow()

            logger.info(
                f"🚀 Zoom Bot起動開始: session_id={session.id}, "
                f"meeting_id={session.meeting_id}"
            )

            # ライブ文字起こしサービスにセッションを作成
            from app.services.live_transcription_service import live_transcription_service
            live_transcription_service.create_session(
                session_id=session.id,
                meeting_id=session.meeting_id,
                meeting_topic=f"会議 {session.meeting_id}"
            )

            from app.config import settings
            from azure.mgmt.containerinstance.models import (
                ContainerGroup,
                Container,
                ContainerGroupRestartPolicy,
                EnvironmentVariable,
                ImageRegistryCredential,
                OperatingSystemTypes,
                ResourceRequests,
                ResourceRequirements,
            )

            container_group_name = f"bot-{session.id[:8]}"
            image = f"{settings.ACR_SERVER}/tech-notta-bot:latest"
            backend_url = settings.BACKEND_URL
            azure_speech_key = settings.AZURE_SPEECH_KEY or ""
            azure_speech_region = settings.AZURE_SPEECH_REGION or "japaneast"

            env_vars = [
                EnvironmentVariable(name="MEETING_NUMBER", value=session.meeting_id),
                EnvironmentVariable(name="JWT_TOKEN", secure_value=jwt_token or ""),
                EnvironmentVariable(name="PASSWORD", value=session.meeting_password or ""),
                EnvironmentVariable(name="BOT_NAME", value=zoom_config.bot_display_name),
                EnvironmentVariable(name="BACKEND_URL", value=backend_url),
                EnvironmentVariable(name="SESSION_ID", value=session.id),
                EnvironmentVariable(name="AZURE_SPEECH_KEY", secure_value=azure_speech_key),
                EnvironmentVariable(name="AZURE_SPEECH_REGION", value=azure_speech_region),
            ]

            container = Container(
                name=container_group_name,
                image=image,
                resources=ResourceRequirements(
                    requests=ResourceRequests(cpu=1.0, memory_in_gb=1.5)
                ),
                environment_variables=env_vars,
            )

            registry_credential = ImageRegistryCredential(
                server=settings.ACR_SERVER,
                username=settings.ACR_USERNAME,
                password=settings.ACR_PASSWORD,
            )

            container_group = ContainerGroup(
                location=settings.ACI_LOCATION,
                containers=[container],
                os_type=OperatingSystemTypes.LINUX,
                restart_policy=ContainerGroupRestartPolicy.NEVER,
                image_registry_credentials=[registry_credential],
            )

            aci_client = self._get_aci_client()
            poller = aci_client.container_groups.begin_create_or_update(
                settings.AZURE_RESOURCE_GROUP,
                container_group_name,
                container_group,
            )
            # ACI の作成完了を待たずに IN_MEETING に遷移（非同期起動）
            await asyncio.get_event_loop().run_in_executor(None, poller.wait)

            session.container_id = container_group_name
            session.status = BotStatus.IN_MEETING
            session.updated_at = datetime.utcnow()
            logger.info(
                f"✅ Zoom Bot参加完了 (ContainerGroup: {container_group_name}): "
                f"session_id={session.id}"
            )

        except Exception as e:
            logger.error(f"Zoom Bot起動エラー: {e}")
            session.status = BotStatus.ERROR
            session.error_message = str(e)
            session.updated_at = datetime.utcnow()

    async def _run_browser_bot(self, session: BotSession) -> None:
        """
        ブラウザBot（Google Meet / Teams）を ACI コンテナグループとして起動して会議に参加
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
            from azure.mgmt.containerinstance.models import (
                ContainerGroup,
                Container,
                ContainerGroupRestartPolicy,
                EnvironmentVariable,
                ImageRegistryCredential,
                OperatingSystemTypes,
                ResourceRequests,
                ResourceRequirements,
            )

            container_group_name = f"bot-{session.id[:8]}"
            image = f"{settings.ACR_SERVER}/tech-notta-browser-bot:latest"
            backend_url = settings.BACKEND_URL
            azure_speech_key = settings.AZURE_SPEECH_KEY or ""
            azure_speech_region = settings.AZURE_SPEECH_REGION or "japaneast"

            if session.platform == BotPlatform.GOOGLE_MEET:
                bot_name = google_meet_config.bot_display_name
            else:
                bot_name = teams_config.bot_display_name

            env_vars = [
                EnvironmentVariable(name="PLATFORM", value=session.platform.value),
                EnvironmentVariable(name="MEETING_URL", value=session.meeting_url or ""),
                EnvironmentVariable(name="MEETING_ID", value=session.meeting_id),
                EnvironmentVariable(name="BOT_NAME", value=bot_name),
                EnvironmentVariable(name="BACKEND_URL", value=backend_url),
                EnvironmentVariable(name="SESSION_ID", value=session.id),
                EnvironmentVariable(name="AZURE_SPEECH_KEY", secure_value=azure_speech_key),
                EnvironmentVariable(name="AZURE_SPEECH_REGION", value=azure_speech_region),
            ]

            container = Container(
                name=container_group_name,
                image=image,
                resources=ResourceRequirements(
                    requests=ResourceRequests(cpu=1.0, memory_in_gb=2.0)
                ),
                environment_variables=env_vars,
            )

            registry_credential = ImageRegistryCredential(
                server=settings.ACR_SERVER,
                username=settings.ACR_USERNAME,
                password=settings.ACR_PASSWORD,
            )

            container_group = ContainerGroup(
                location=settings.ACI_LOCATION,
                containers=[container],
                os_type=OperatingSystemTypes.LINUX,
                restart_policy=ContainerGroupRestartPolicy.NEVER,
                image_registry_credentials=[registry_credential],
            )

            aci_client = self._get_aci_client()
            poller = aci_client.container_groups.begin_create_or_update(
                settings.AZURE_RESOURCE_GROUP,
                container_group_name,
                container_group,
            )
            await asyncio.get_event_loop().run_in_executor(None, poller.wait)

            session.container_id = container_group_name
            session.status = BotStatus.IN_MEETING
            session.updated_at = datetime.utcnow()
            logger.info(
                f"✅ ブラウザBot参加完了 (ContainerGroup: {container_group_name}): "
                f"session_id={session.id}"
            )

        except Exception as e:
            logger.error(f"ブラウザBot起動エラー: {e}")
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
        Botを会議から退出させる（ACI コンテナグループを削除）

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

        # ACI コンテナグループ削除
        if session.container_id:
            try:
                from app.config import settings
                aci_client = self._get_aci_client()
                poller = aci_client.container_groups.begin_delete(
                    settings.AZURE_RESOURCE_GROUP,
                    session.container_id,
                )
                await asyncio.get_event_loop().run_in_executor(None, poller.wait)
            except Exception as e:
                logger.error(f"ACIコンテナグループ削除エラー: {e}")

        session.status = BotStatus.COMPLETED
        session.updated_at = datetime.utcnow()

        logger.info(f"✅ Bot退出完了: session_id={session_id}")
        return True


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
