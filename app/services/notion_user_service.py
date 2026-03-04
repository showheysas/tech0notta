"""
NotionユーザーDBからメール→ページID解決 + 案件メンバーシップ取得
"""
import logging
from typing import Optional

from cachetools import TTLCache
from notion_client import Client

from app.config import settings

logger = logging.getLogger(__name__)


class NotionUserService:
    """NotionユーザーDBからメール→ページID解決 + 案件メンバーシップ取得"""

    def __init__(self):
        self.enabled = bool(settings.NOTION_API_KEY and settings.NOTION_USER_DB_ID)
        if self.enabled:
            self.client = Client(auth=settings.NOTION_API_KEY)
        # TTLキャッシュ
        self._email_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)      # 1時間
        self._membership_cache: TTLCache = TTLCache(maxsize=50, ttl=300)   # 5分

    async def resolve_by_email(self, email: str) -> Optional[str]:
        """email → Notion ユーザー情報DB ページID"""
        cached = self._email_cache.get(email)
        if cached is not None:
            return cached if cached != "__NOT_FOUND__" else None

        if not self.enabled:
            return None

        try:
            results = self.client.databases.query(
                database_id=settings.NOTION_USER_DB_ID,
                filter={"property": "メールアドレス", "email": {"equals": email}},
            )
            if results["results"]:
                page_id = results["results"][0]["id"]
                self._email_cache[email] = page_id
                logger.info(f"Resolved email {email} → Notion page {page_id}")
                return page_id
        except Exception as e:
            logger.error(f"Error resolving email {email} in Notion: {e}")

        self._email_cache[email] = "__NOT_FOUND__"
        return None

    async def get_project_ids_for_user(self, notion_user_page_id: str) -> set[str]:
        """ユーザーが所属する案件IDセットを返す"""
        cached = self._membership_cache.get(notion_user_page_id)
        if cached is not None:
            return cached

        try:
            results = self.client.databases.query(
                database_id=settings.NOTION_PROJECT_DB_ID,
                filter={
                    "property": "メンバー",
                    "relation": {"contains": notion_user_page_id},
                },
            )
            project_ids = {p["id"] for p in results.get("results", [])}
            self._membership_cache[notion_user_page_id] = project_ids
            logger.info(
                f"User {notion_user_page_id} belongs to {len(project_ids)} projects"
            )
            return project_ids
        except Exception as e:
            logger.error(
                f"Error getting project membership for {notion_user_page_id}: {e}"
            )
            return set()


_notion_user_service: Optional[NotionUserService] = None


def get_notion_user_service() -> NotionUserService:
    global _notion_user_service
    if _notion_user_service is None:
        _notion_user_service = NotionUserService()
    return _notion_user_service
