"""後方互換: app.services.notion パッケージへの re-export"""
from app.services.notion import NotionService, get_notion_service, get_notion_client

__all__ = ["NotionService", "get_notion_service", "get_notion_client"]
