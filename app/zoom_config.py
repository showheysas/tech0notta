"""Zoom関連の設定"""
import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

class ZoomConfig(BaseSettings):
    """Zoom API・Webhook設定"""
    
    # Webhook設定
    webhook_secret_token: str = ""
    
    # Server-to-Server OAuth設定
    account_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    
    # Meeting SDK設定
    sdk_key: str = ""
    sdk_secret: str = ""
    
    # Bot設定
    bot_display_name: str = "Tech Bot"
    
    # API設定
    api_base_url: str = "https://api.zoom.us/v2"
    oauth_token_url: str = "https://zoom.us/oauth/token"
    
    model_config = SettingsConfigDict(
        env_prefix="ZOOM_",
        env_file=".env",
        extra="ignore"
    )

    def log_settings(self):
        """設定値をログ出力（機密情報はマスク）"""
        logger.info(f"Zoom Config Loaded: AccountID={self.account_id}, ClientID={self.client_id[:4]}***")


# シングルトンインスタンス
zoom_config = ZoomConfig()
