"""Notion サービス基底クラス - クライアント初期化と共通設定"""
import logging

from notion_client import Client

from app.config import settings

logger = logging.getLogger(__name__)


class NotionServiceBase:
    """Notion API クライアントの初期化と共通プロパティを提供する基底クラス"""

    def __init__(self):
        self.enabled = bool(settings.NOTION_API_KEY and settings.NOTION_DATABASE_ID)
        if self.enabled:
            self.client = Client(auth=settings.NOTION_API_KEY)
            self.database_id = settings.NOTION_DATABASE_ID
            self.meeting_database_id = settings.NOTION_DATABASE_ID
            self.task_database_id = settings.NOTION_TASK_DB_ID
            self.project_database_id = settings.NOTION_PROJECT_DB_ID
            logger.info(
                f"Notion integration enabled. Meeting DB: {self.meeting_database_id}, "
                f"Task DB: {self.task_database_id}, Project DB: {self.project_database_id}"
            )
        else:
            logger.warning("Notion API key or Database ID not set. Notion integration disabled.")
