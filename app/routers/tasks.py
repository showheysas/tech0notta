from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Set
from datetime import date
from app.models.task import (
    TaskExtractRequest,
    TaskExtractResponse,
    TaskDecomposeRequest,
    TaskDecomposeResponse,
    TaskRegisterRequest,
    TaskRegisterResponse,
    TaskUpdate,
    TaskResponse,
    TaskStatus,
    TaskPriority,
)
from app.models.user import User
from app.auth import get_current_user, get_authorized_project_ids
from app.services.task_service import get_task_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# --- タスク抽出・分解・登録 ---


@router.post("/extract", response_model=TaskExtractResponse)
async def extract_tasks(
    request: TaskExtractRequest,
    current_user: User = Depends(get_current_user),
):
    """
    議事録からタスクを自動抽出する

    Azure OpenAIを使用して議事録の要約からアクションアイテムを抽出します。
    """
    service = get_task_service()
    return await service.extract_tasks(request)


@router.post("/decompose", response_model=TaskDecomposeResponse)
async def decompose_task(
    request: TaskDecomposeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    抽象的なタスクを具体的なサブタスクに分解する

    Azure OpenAIを使用して3-5個の具体的なステップに分解します。
    """
    service = get_task_service()
    return await service.decompose_task(request)


@router.post("/register", response_model=TaskRegisterResponse)
async def register_tasks(
    request: TaskRegisterRequest,
    current_user: User = Depends(get_current_user),
):
    """
    承認されたタスクをNotion Task DBに登録する
    """
    service = get_task_service()
    return await service.register_tasks(request)


# --- タスクCRUD ---


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    project_id: Optional[str] = Query(None, description="プロジェクトIDでフィルター"),
    assignee: Optional[str] = Query(None, description="担当者でフィルター"),
    status: Optional[TaskStatus] = Query(None, description="ステータスでフィルター"),
    priority: Optional[TaskPriority] = Query(None, description="優先度でフィルター"),
    due_date_from: Optional[date] = Query(None, description="期限開始日"),
    due_date_to: Optional[date] = Query(None, description="期限終了日"),
    sort_by: str = Query("due_date", description="ソートキー"),
    sort_order: str = Query("asc", description="ソート順（asc/desc）"),
    authorized_ids: Optional[Set[str]] = Depends(get_authorized_project_ids),
):
    """
    タスク一覧を取得する（フィルター・ソート対応）
    管理者は全件、一般ユーザーは所属案件のタスクのみ。
    """
    service = get_task_service()
    tasks = await service.get_tasks(
        project_id=project_id,
        assignee=assignee,
        status=status,
        priority=priority,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    # 認可フィルタ（None=管理者=全件）
    if authorized_ids is not None:
        tasks = [
            t for t in tasks
            if t.project_id and t.project_id in authorized_ids
        ]

    return tasks


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    タスク詳細を取得する
    """
    service = get_task_service()
    return await service.get_task(task_id)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    data: TaskUpdate,
    current_user: User = Depends(get_current_user),
):
    """
    タスクを更新する

    ステータスが「完了」に変更された場合、completion_dateが自動設定されます。
    必須フィールド: title, due_date
    """
    service = get_task_service()
    return await service.update_task(task_id, data)


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    タスクを削除する
    """
    service = get_task_service()
    await service.delete_task(task_id)
    return {"message": "タスクを削除しました"}
