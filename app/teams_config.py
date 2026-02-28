"""Microsoft Teams Bot設定"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class TeamsConfig(BaseSettings):
    """Microsoft Teams Bot設定"""
    model_config = SettingsConfigDict(
        env_prefix="TEAMS_",
        env_file=".env",
        extra="ignore"
    )

    bot_display_name: str = "Tech Bot"  # TEAMS_BOT_DISPLAY_NAME


# シングルトンインスタンス
teams_config = TeamsConfig()
