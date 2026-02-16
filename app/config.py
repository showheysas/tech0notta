from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )

    # Database (defaults to SQLite for local dev)
    DATABASE_URL: str = "sqlite:///./meeting_notes.db"

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING: str | None = None
    AZURE_STORAGE_CONTAINER_NAME: str = "audio-files"

    # Azure Speech Service
    AZURE_SPEECH_KEY: str | None = None
    AZURE_SPEECH_REGION: str = "japaneast"
    AZURE_SPEECH_API_VERSION: str = "2025-10-15"
    AZURE_SPEECH_ENDPOINT: str = ""

    # Azure OpenAI
    AZURE_OPENAI_API_KEY: str | None = None
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_DEPLOYMENT_NAME: str = "gpt-4o"
    AZURE_OPENAI_API_VERSION: str = "2024-08-01-preview"

    # Notion (optional)
    NOTION_API_KEY: str = ""
    NOTION_DATABASE_ID: str = ""
    NOTION_CUSTOMER_DB_ID: str = ""
    NOTION_DEAL_DB_ID: str = ""
    NOTION_TASK_DB_ID: str = ""
    NOTION_PROJECT_DB_ID: str = ""

    # Slack
    SLACK_BOT_TOKEN: str | None = None
    SLACK_CHANNEL_ID: str | None = None
    SLACK_SIGNING_SECRET: str | None = None  # Slackからのリクエスト検証用（将来の拡張用）

    # Zoom Webhook
    ZOOM_WEBHOOK_SECRET_TOKEN: str | None = None

    # Zoom Server-to-Server OAuth
    ZOOM_ACCOUNT_ID: str | None = None
    ZOOM_CLIENT_ID: str | None = None
    ZOOM_CLIENT_SECRET: str | None = None

    # Zoom Meeting SDK
    ZOOM_SDK_KEY: str | None = None
    ZOOM_SDK_SECRET: str | None = None

    # Application
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    MAX_FILE_SIZE_MB: int = 200

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


settings = Settings()
