"""Jobs デバッグエンドポイント"""
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/debug/notion-task-config")
async def debug_notion_task_config():
    """Notion Task DB の接続設定を診断する（デバッグ用）"""
    from app.config import settings

    result = {
        "notion_api_key_set": bool(settings.NOTION_API_KEY),
        "notion_database_id_set": bool(settings.NOTION_DATABASE_ID),
        "notion_task_db_id_set": bool(settings.NOTION_TASK_DB_ID),
        "notion_task_db_id_value": settings.NOTION_TASK_DB_ID[:8] + "..." if settings.NOTION_TASK_DB_ID else "(empty)",
        "notion_project_db_id_set": bool(settings.NOTION_PROJECT_DB_ID),
        "notion_user_db_id_set": bool(settings.NOTION_USER_DB_ID),
    }

    try:
        from app.services.notion_task_service import get_notion_task_service
        task_service = get_notion_task_service()
        result["notion_task_service_enabled"] = task_service.enabled
    except Exception as e:
        result["notion_task_service_error"] = str(e)

    try:
        from app.services.notion_client import get_notion_service
        notion_service = get_notion_service()
        result["notion_service_enabled"] = notion_service.enabled
    except Exception as e:
        result["notion_service_error"] = str(e)

    return result
