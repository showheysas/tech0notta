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
    NOTION_USER_DB_ID: str = ""        # ユーザー情報DB ID（認可用）

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

    # Azure Container Apps (ACA) - Bot 実行基盤
    AZURE_SUBSCRIPTION_ID: str | None = None
    AZURE_RESOURCE_GROUP: str | None = None
    ACA_BOT_JOB_NAME: str | None = None    # e.g. "job-bot-tech0notta"
    ACA_BOT_IMAGE: str | None = None       # e.g. "acr002tech0nottadev.azurecr.io/tech0notta-bot:latest"
    BACKEND_URL: str = "http://localhost:8000"

    # ACR (Bot イメージレジストリ)
    ACR_SERVER: str | None = None      # e.g. myregistry.azurecr.io
    ACR_USERNAME: str | None = None
    ACR_PASSWORD: str | None = None

    # Azure AD / Entra ID 認証
    AZURE_AD_TENANT_ID: str | None = None
    AZURE_AD_CLIENT_ID: str | None = None

    # Application
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,https://techn0tta-frontend-sho-v2.vercel.app"
    MAX_FILE_SIZE_MB: int = 200

    @property
    def azure_jwks_uri(self) -> str:
        return f"https://login.microsoftonline.com/{self.AZURE_AD_TENANT_ID}/discovery/v2.0/keys"

    @property
    def azure_ad_issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.AZURE_AD_TENANT_ID}/v2.0"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


settings = Settings()
