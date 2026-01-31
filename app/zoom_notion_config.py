
import os
from pydantic_settings import BaseSettings

class NotionSettings(BaseSettings):
    """Notion設定"""
    NOTION_API_KEY: str = ""
    NOTION_DATABASE_ID: str = ""

    class Config:
        env_file = ".env"
        # .envファイルがない場合でもエラーにしない（Docker環境など）
        env_file_encoding = "utf-8"
        # 定義されていない環境変数を無視する
        extra = "ignore"

notion_settings = NotionSettings()
