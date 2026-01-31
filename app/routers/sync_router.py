
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from app.services.zoom_notion_service import zoom_notion_service

router = APIRouter(
    prefix="/api/sync",
    tags=["sync"],
    responses={404: {"description": "Not found"}},
)

class SyncRequest(BaseModel):
    title: str
    summary: str
    tags: List[str]

@router.post("/notion")
async def sync_to_notion(request: SyncRequest):
    """
    Notionに議事録を同期する
    """
    try:
        result = await zoom_notion_service.create_meeting_note(
            title=request.title,
            summary=request.summary,
            tags=request.tags
        )
        return {"status": "success", "url": result.get("url"), "id": result.get("id")}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 詳細なエラーはログに出力済み
        raise HTTPException(status_code=500, detail="Failed to sync to Notion")
