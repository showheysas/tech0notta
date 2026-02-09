from fastapi import APIRouter
from app.models.notification import (
    MeetingApprovedNotification,
    TaskAssignedNotification,
    ReminderBatchResponse,
    NotificationResponse,
)
from app.services.notification_service import get_notification_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.post("/meeting-approved", response_model=NotificationResponse)
async def send_meeting_approved_notification(
    notification: MeetingApprovedNotification,
):
    """
    議事録承認通知をSlackプロジェクトチャネルに送信する

    メッセージにはタイトル、日付、要約抜粋、Notionページリンクを含みます。
    """
    service = get_notification_service()
    return await service.send_meeting_approved_notification(notification)


@router.post("/task-assigned", response_model=NotificationResponse)
async def send_task_assigned_notification(
    notification: TaskAssignedNotification,
):
    """
    タスク割り当て通知を担当者にSlack DMで送信する

    メッセージにはタスク名、プロジェクト名、期限、優先度、Notionリンクを含みます。
    """
    service = get_notification_service()
    return await service.send_task_assigned_notification(notification)


@router.get("/batch/reminder", response_model=ReminderBatchResponse)
async def run_reminder_batch():
    """
    リマインダーバッチを実行する

    期限3日前および当日のタスク（未完了）を対象に、担当者へSlack DMを送信します。
    """
    service = get_notification_service()
    return await service.run_reminder_batch()
