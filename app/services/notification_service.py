"""
通知サービス - Slack通知のビジネスロジック

議事録承認通知、タスク割り当て通知、リマインダー通知を担当します。
Slack Block Kit形式でメッセージを構築し、リトライ処理を行います。
"""
from typing import Optional
from app.models.notification import (
    MeetingApprovedNotification,
    TaskAssignedNotification,
    ReminderBatchResponse,
    NotificationResponse,
)
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """Slack通知サービス"""

    async def send_meeting_approved_notification(
        self, notification: MeetingApprovedNotification
    ) -> NotificationResponse:
        """
        議事録承認通知をSlackプロジェクトチャネルに送信する

        メッセージにはタイトル、日付、要約抜粋、Notionページリンクを含みます。
        Slack APIエラー時は3回リトライします。

        Args:
            notification: 議事録承認通知リクエスト

        Returns:
            通知レスポンス

        Raises:
            HTTPException: Slack APIエラー（リトライ後も失敗した場合）
        """
        # TODO: Slack API連携による議事録承認通知を実装
        raise NotImplementedError(
            "Meeting approved notification not yet implemented"
        )

    async def send_task_assigned_notification(
        self, notification: TaskAssignedNotification
    ) -> NotificationResponse:
        """
        タスク割り当て通知を担当者にSlack DMで送信する

        メッセージにはタスク名、プロジェクト名、期限、優先度、Notionリンクを含みます。
        担当者のSlack IDが見つからない場合はスキップしてログに記録します。

        Args:
            notification: タスク割り当て通知リクエスト

        Returns:
            通知レスポンス

        Raises:
            HTTPException: Slack APIエラー（リトライ後も失敗した場合）
        """
        # TODO: Slack API連携によるタスク割り当て通知を実装
        raise NotImplementedError(
            "Task assigned notification not yet implemented"
        )

    async def run_reminder_batch(self) -> ReminderBatchResponse:
        """
        リマインダーバッチを実行する

        期限3日前および当日のタスク（未完了）を対象に、担当者へSlack DMを送信します。
        同一タスク・同一日の重複送信を防止します。

        Returns:
            バッチ実行結果
        """
        # TODO: リマインダーバッチ処理を実装
        raise NotImplementedError("Reminder batch not yet implemented")


# シングルトンインスタンス
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """NotificationServiceのシングルトンインスタンスを取得"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
