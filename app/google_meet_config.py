"""Google Meet Bot設定"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class GoogleMeetConfig(BaseSettings):
    """Google Meet Bot設定"""
    model_config = SettingsConfigDict(
        env_prefix="GOOGLE_MEET_",
        env_file=".env",
        extra="ignore"
    )

    bot_display_name: str = "Tech Bot"  # GOOGLE_MEET_BOT_DISPLAY_NAME


# シングルトンインスタンス
google_meet_config = GoogleMeetConfig()
