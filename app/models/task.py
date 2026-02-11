from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


class TaskPriority(str, Enum):
    """タスク優先度"""
    HIGH = "高"
    MEDIUM = "中"
    LOW = "低"


class TaskStatus(str, Enum):
    """タスクステータス"""
    NOT_STARTED = "未着手"
    IN_PROGRESS = "進行中"
    COMPLETED = "完了"


# --- タスク抽出 ---

class TaskExtractRequest(BaseModel):
    """タスク抽出リクエスト"""
    job_id: str
    summary: str
    meeting_date: date


class ExtractedTask(BaseModel):
    """抽出されたタスク"""
    title: str
    description: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[date] = None
    is_abstract: bool = False  # 分解が必要かどうか


class TaskExtractResponse(BaseModel):
    """タスク抽出レスポンス"""
    job_id: str
    tasks: List[ExtractedTask]


# --- タスク分解 ---

class TaskDecomposeRequest(BaseModel):
    """タスク分解リクエスト"""
    task_title: str
    task_description: Optional[str] = None
    parent_due_date: date


class SubTaskItem(BaseModel):
    """サブタスクアイテム"""
    title: str
    description: Optional[str] = None
    order: int


class TaskDecomposeResponse(BaseModel):
    """タスク分解レスポンス"""
    parent_task: str
    subtasks: List[SubTaskItem]


# --- タスク登録 ---

class SubTaskCreate(BaseModel):
    """サブタスク作成"""
    title: str
    description: Optional[str] = None
    order: int


class TaskCreate(BaseModel):
    """タスク作成"""
    title: str
    description: Optional[str] = None
    assignee: Optional[str] = None
    due_date: date
    priority: TaskPriority = TaskPriority.MEDIUM
    subtasks: Optional[List[SubTaskCreate]] = None


class TaskToRegister(BaseModel):
    """登録用タスク（MVP新機能）"""
    title: str
    description: Optional[str] = None
    assignee: str = "未割り当て"
    due_date: date
    priority: TaskPriority = TaskPriority.MEDIUM
    subtasks: List[SubTaskItem] = []


class TaskRegisterRequest(BaseModel):
    """タスク登録リクエスト"""
    job_id: str
    project_id: Optional[str] = None
    meeting_page_id: Optional[str] = None  # 議事録のNotion Page ID
    tasks: List[TaskToRegister]


class TaskRegisterResponse(BaseModel):
    """タスク登録レスポンス"""
    job_id: str
    registered_count: int
    task_ids: List[str]


# --- タスク更新 ---

class TaskUpdate(BaseModel):
    """タスク更新リクエスト"""
    title: Optional[str] = None
    description: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None


# --- タスクレスポンス ---

class TaskResponse(BaseModel):
    """タスクレスポンス"""
    id: str
    title: str
    description: Optional[str] = None
    assignee: Optional[str] = None
    due_date: date
    status: TaskStatus
    priority: TaskPriority
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    meeting_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    subtask_count: int = 0
    completed_subtask_count: int = 0
    is_overdue: bool = False
    completion_date: Optional[date] = None
    notion_page_url: str = ""
    created_at: datetime
    updated_at: datetime
