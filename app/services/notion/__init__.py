"""
Notion サービスパッケージ

NotionService は meeting / project / content_builder の機能を統合した
ファサードクラス。既存の get_notion_service() / get_notion_client() を維持する。
"""
from app.services.notion.meeting_service import NotionMeetingService
from app.services.notion.project_service import NotionProjectService


class NotionService(NotionMeetingService, NotionProjectService):
    """
    議事録・案件操作を統合した Notion サービス。

    MRO: NotionMeetingService → NotionProjectService → NotionServiceBase
    両方とも NotionServiceBase.__init__ を共有するため、
    クライアント初期化は一度だけ行われる。
    """
    pass


_notion_service = None


def get_notion_service() -> NotionService:
    global _notion_service
    if _notion_service is None:
        _notion_service = NotionService()
    return _notion_service


def get_notion_client() -> NotionService:
    """get_notion_serviceのエイリアス"""
    return get_notion_service()
