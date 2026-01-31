"""
Zoom 認証サービス
Server-to-Server OAuthでアクセストークンを取得・管理する
"""
import base64
import logging
import time
from typing import Optional

import httpx

from app.zoom_config import zoom_config

logger = logging.getLogger(__name__)


class ZoomAuthService:
    """Zoom Server-to-Server OAuth認証サービス"""
    
    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
    
    def _is_token_valid(self) -> bool:
        """トークンがまだ有効かどうかを確認（60秒のバッファ付き）"""
        return (
            self._access_token is not None
            and time.time() < self._token_expires_at - 60
        )
    
    def _create_auth_header(self) -> str:
        """Basic認証ヘッダーを生成"""
        # 値の前後の空白を除去
        client_id = zoom_config.client_id.strip()
        client_secret = zoom_config.client_secret.strip()
        
        credentials = f"{client_id}:{client_secret}"
        encoded = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        return f"Basic {encoded}"
    
    async def get_access_token(self) -> Optional[str]:
        """
        アクセストークンを取得
        キャッシュされたトークンが有効な場合はそれを返す
        
        Returns:
            アクセストークン、または取得に失敗した場合はNone
        """
        # キャッシュされたトークンが有効な場合はそれを使用
        if self._is_token_valid():
            logger.debug("キャッシュされたアクセストークンを使用")
            return self._access_token
        
        # 設定チェック
        if not all([
            zoom_config.account_id,
            zoom_config.client_id,
            zoom_config.client_secret
        ]):
            logger.error(
                "Zoom OAuth設定が不完全です。"
                "ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET を設定してください。"
            )
            return None
        
        # 新しいトークンを取得
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    zoom_config.oauth_token_url,
                    headers={
                        "Authorization": self._create_auth_header(),
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    params={
                        "grant_type": "account_credentials",
                        "account_id": zoom_config.account_id
                    },
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(
                        f"アクセストークンの取得に失敗: "
                        f"status={response.status_code}, body={response.text}"
                    )
                    return None
                
                data = response.json()
                self._access_token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                self._token_expires_at = time.time() + expires_in
                
                logger.info(
                    f"アクセストークンを取得しました "
                    f"(有効期限: {expires_in}秒)"
                )
                return self._access_token
                
        except httpx.RequestError as e:
            logger.error(f"アクセストークン取得中にエラーが発生: {e}")
            return None
    
    def clear_token(self) -> None:
        """キャッシュされたトークンをクリア"""
        self._access_token = None
        self._token_expires_at = 0
        logger.debug("アクセストークンのキャッシュをクリアしました")


# シングルトンインスタンス
zoom_auth_service = ZoomAuthService()
