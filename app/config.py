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
    AZURE_STORAGE_CONNECTION_STRING: str
    AZURE_STORAGE_CONTAINER_NAME: str = "audio-files"

    # Azure Speech Service
    AZURE_SPEECH_KEY: str
    AZURE_SPEECH_REGION: str = "japaneast"
    AZURE_SPEECH_API_VERSION: str = "2025-10-15"
    AZURE_SPEECH_ENDPOINT: str = ""

    # Azure OpenAI
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_DEPLOYMENT_NAME: str = "gpt-4o"
    AZURE_OPENAI_API_VERSION: str = "2024-08-01-preview"

    # Notion (optional)
    NOTION_API_KEY: str = ""
    NOTION_DATABASE_ID: str = ""

    # Application
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    MAX_FILE_SIZE_MB: int = 100

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


settings = Settings()
