"""
案件（プロジェクト）管理API

Notion案件DBとの連携を担当する。
- 案件一覧取得（Notionから直接取得）
- 案件作成
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.services.notion_client import get_notion_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectResponse(BaseModel):
    """案件レスポンス"""
    id: str
    name: str
    status: str = ""
    importance: str = ""
    company_name: Optional[str] = None
    amount: Optional[int] = None
    expected_close_date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    url: str = ""


class ProjectCreateRequest(BaseModel):
    """案件作成リクエスト"""
    name: str
    status: Optional[str] = None
    importance: Optional[str] = None
    situation: Optional[str] = None
    department: Optional[str] = None
    amount: Optional[int] = None
    expected_close_date: Optional[str] = None
    director: Optional[List[str]] = None
    pdm: Optional[List[str]] = None
    biz: Optional[List[str]] = None
    tech: Optional[List[str]] = None
    design: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    dropbox_url: Optional[str] = None


@router.get("", response_model=List[ProjectResponse])
async def list_projects():
    """
    Notion案件DBから案件一覧を取得する。
    議事録作成時の案件選択に使用。
    """
    try:
        notion = get_notion_service()
        projects = await notion.list_projects()
        
        return [
            ProjectResponse(
                id=p["id"],
                name=p.get("name", ""),
                status=p.get("status", ""),
                importance=p.get("importance", ""),
                company_name=p.get("company_name"),
                amount=p.get("amount"),
                expected_close_date=p.get("expected_close_date"),
                start_date=p.get("start_date"),
                end_date=p.get("end_date"),
                url=p.get("url", ""),
            )
            for p in projects
        ]
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=f"案件一覧の取得に失敗しました: {str(e)}")


@router.post("", response_model=ProjectResponse)
async def create_project(request: ProjectCreateRequest):
    """
    Notion案件DBに案件を作成する
    """
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="案件名は必須です")
    
    try:
        notion = get_notion_service()
        result = await notion.create_project_record(request.model_dump(exclude_none=True))
        
        if not result:
            raise HTTPException(status_code=500, detail="案件の作成に失敗しました（Notion未設定）")
        
        return ProjectResponse(
            id=result["id"],
            name=result.get("name", request.name),
            url=result.get("url", ""),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        raise HTTPException(status_code=500, detail=f"案件の作成に失敗しました: {str(e)}")
