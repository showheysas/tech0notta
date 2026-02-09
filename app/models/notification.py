from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# --- 議事録承認通知 ---

class MeetingApprovedNotification(BaseModel):
    """議事録承認通知リクエスト"""
    job_id: str
    channel_id: str


# --- タスク割り当て通知 ---

class TaskAssignedNotification(BaseModel):
    """タスク割り当て通知リクエスト"""
    task_id: str
    assignee_slack_id: str


# --- リマインダーバッチ ---

class ReminderBatchResponse(BaseModel):
    """リマインダーバッチレスポンス"""
    processed_count: int
    sent_count: int
    failed_count: int
    errors: List[str]


# --- 通知レスポンス ---

class NotificationResponse(BaseModel):
    """通知レスポンス"""
    id: str
    type: str  # 'meeting_completed', 'task_assigned', 'reminder'
    job_id: Optional[str] = None
    task_id: Optional[str] = None
    recipient_slack_id: str
    channel_id: Optional[str] = None
    status: str = "pending"  # 'pending', 'sent', 'failed'
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
