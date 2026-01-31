"""
Zoom APIサービス
会議詳細の取得などZoom REST APIを呼び出す
"""
import logging
from typing import Any, Optional

import httpx

from app.zoom_config import zoom_config
from app.services.zoom_auth_service import zoom_auth_service

logger = logging.getLogger(__name__)


class MeetingDetails:
    """会議詳細情報"""
    
    def __init__(
        self,
        meeting_id: str,
        topic: str,
        join_url: str,
        password: Optional[str] = None,
        encrypted_password: Optional[str] = None,
        host_id: Optional[str] = None,
        start_time: Optional[str] = None,
        duration: Optional[int] = None,
        raw_response: Optional[dict] = None
    ):
        self.meeting_id = meeting_id
        self.topic = topic
        self.join_url = join_url
        self.password = password
        self.encrypted_password = encrypted_password
        self.host_id = host_id
        self.start_time = start_time
        self.duration = duration
        self.raw_response = raw_response
    
    def get_join_url_with_password(self) -> str:
        """
        パスワード付きの参加URLを取得
        
        join_urlにすでにpwdパラメータが含まれている場合はそのまま返す。
        含まれていない場合は、encrypted_passwordがあれば追加する。
        """
        if "pwd=" in self.join_url:
            return self.join_url
        
        if self.encrypted_password:
            separator = "&" if "?" in self.join_url else "?"
            return f"{self.join_url}{separator}pwd={self.encrypted_password}"
        
        return self.join_url
    
    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "meeting_id": self.meeting_id,
            "topic": self.topic,
            "join_url": self.join_url,
            "join_url_with_password": self.get_join_url_with_password(),
            "password": self.password,
            "encrypted_password": self.encrypted_password,
            "host_id": self.host_id,
            "start_time": self.start_time,
            "duration": self.duration
        }


class ZoomApiService:
    """Zoom REST APIサービス"""
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Optional[dict]:
        """
        Zoom APIにリクエストを送信
        
        Args:
            method: HTTPメソッド
            endpoint: APIエンドポイント（/meetings/{id}など）
            **kwargs: httpxに渡す追加引数
        
        Returns:
            JSONレスポンス、または失敗時はNone
        """
        token = await zoom_auth_service.get_access_token()
        if not token:
            logger.error("アクセストークンがないためAPIリクエストを送信できません")
            return None
        
        url = f"{zoom_config.api_base_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method,
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0,
                    **kwargs
                )
                
                if response.status_code == 401:
                    # トークンが無効な場合はクリアして再試行
                    logger.warning("トークンが無効です。クリアして再試行します。")
                    zoom_auth_service.clear_token()
                    return await self._make_request(method, endpoint, **kwargs)
                
                if response.status_code != 200:
                    logger.error(
                        f"API呼び出しに失敗: {method} {endpoint} "
                        f"status={response.status_code}, body={response.text}"
                    )
                    return None
                
                return response.json()
                
        except httpx.RequestError as e:
            logger.error(f"API呼び出し中にエラーが発生: {e}")
            return None
    
    async def get_meeting_details(
        self,
        meeting_id: str
    ) -> Optional[MeetingDetails]:
        """
        会議詳細を取得
        
        Args:
            meeting_id: 会議ID
        
        Returns:
            MeetingDetails、または取得に失敗した場合はNone
        """
        logger.info(f"会議詳細を取得中: meeting_id={meeting_id}")
        
        data = await self._make_request("GET", f"/meetings/{meeting_id}")
        
        if not data:
            return None
        
        details = MeetingDetails(
            meeting_id=str(data.get("id", "")),
            topic=data.get("topic", ""),
            join_url=data.get("join_url", ""),
            password=data.get("password"),
            encrypted_password=data.get("encrypted_password"),
            host_id=data.get("host_id"),
            start_time=data.get("start_time"),
            duration=data.get("duration"),
            raw_response=data
        )
        
        logger.info(
            f"会議詳細を取得しました: "
            f"meeting_id={details.meeting_id}, "
            f"topic='{details.topic}', "
            f"has_password={details.password is not None}"
        )
        
        return details


# シングルトンインスタンス
zoom_api_service = ZoomApiService()
