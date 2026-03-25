from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from app.config import settings
from app.models.job import Job
import logging
from datetime import timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# 日本時間のタイムゾーン
JST = timezone(timedelta(hours=9))


class SlackService:
    """Slack通知サービス"""
    
    def __init__(self):
        if settings.SLACK_BOT_TOKEN:
            self.client = WebClient(token=settings.SLACK_BOT_TOKEN)
        else:
            self.client = None
            logger.warning("SLACK_BOT_TOKEN not configured")
    
    async def send_meeting_approved_notification(
        self,
        job_id: str,
        filename: str,
        summary: str,
        notion_url: Optional[str] = None,
        tasks_count: int = 0
    ) -> dict:
        """
        議事録承認通知を送信（スレッド形式）
        
        メインメッセージ: タイトルのみ
        スレッド返信: 詳細情報
        
        Args:
            job_id: ジョブID
            filename: ファイル名
            summary: 要約テキスト
            notion_url: NotionページURL
            tasks_count: 登録されたタスク数
            
        Returns:
            Slack APIの応答
        """
        if not self.client or not settings.SLACK_CHANNEL_ID:
            logger.warning("Slack not configured, skipping notification")
            return {"ok": False, "error": "not_configured"}
        
        try:
            # 1. メインメッセージを投稿（タイトルのみ）
            main_message_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ *議事録が承認されました*\n📄 {filename}"
                    }
                }
            ]
            
            # タスク数があれば表示
            if tasks_count > 0:
                main_message_blocks[0]["text"]["text"] += f"\n📋 {tasks_count}個のタスクが登録されました"
            
            main_response = self.client.chat_postMessage(
                channel=settings.SLACK_CHANNEL_ID,
                text=f"議事録が承認されました: {filename}",
                blocks=main_message_blocks
            )
            
            if not main_response.get("ok"):
                logger.error(f"Failed to post main message: {main_response}")
                return main_response
            
            # メインメッセージのタイムスタンプを取得（スレッド返信用）
            thread_ts = main_response["ts"]
            
            # 2. スレッド返信で詳細情報を投稿
            detail_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📋 詳細情報"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*ファイル名:* {filename}"
                    }
                },
                {
                    "type": "divider"
                }
            ]
            
            # 要約を追加（スレッド内なので長めに）
            if summary:
                summary_text = summary[:3000] + "..." if len(summary) > 3000 else summary
                detail_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*議事録要約:*\n{summary_text}"
                    }
                })
            
            # Notion URLがあれば追加
            if notion_url:
                detail_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📝 <{notion_url}|Notionで詳細を見る>"
                    }
                })
            
            thread_response = self.client.chat_postMessage(
                channel=settings.SLACK_CHANNEL_ID,
                text="詳細情報",
                blocks=detail_blocks,
                thread_ts=thread_ts  # スレッド返信として投稿
            )
            
            if thread_response.get("ok"):
                logger.info(f"Meeting approved thread notification sent for job: {job_id}")
            else:
                logger.error(f"Failed to post thread reply: {thread_response}")
            
            return main_response
            
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}", exc_info=True)
            raise

    async def send_task_assigned_notification(
        self,
        user_id: str,
        task_title: str,
        project_name: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: str = "中",
        notion_url: Optional[str] = None
    ) -> dict:
        """
        タスク割り当て通知を送信（MVP新機能）
        
        Args:
            user_id: Slack User ID
            task_title: タスク名
            project_name: プロジェクト名
            due_date: 期限
            priority: 優先度
            notion_url: NotionページURL
            
        Returns:
            Slack APIの応答
        """
        if not self.client:
            logger.warning("Slack not configured, skipping notification")
            return {"ok": False, "error": "not_configured"}
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📋 新しいタスクが割り当てられました"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*タスク名:*\n{task_title}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*優先度:*\n{priority}"
                    }
                ]
            }
        ]
        
        if project_name or due_date:
            fields = []
            if project_name:
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*プロジェクト:*\n{project_name}"
                })
            if due_date:
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*期限:*\n{due_date}"
                })
            blocks.append({
                "type": "section",
                "fields": fields
            })
        
        if notion_url:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📝 <{notion_url}|詳細を見る>"
                }
            })
        
        try:
            response = self.client.chat_postMessage(
                channel=user_id,  # DMを送信
                text=f"新しいタスクが割り当てられました: {task_title}",
                blocks=blocks
            )
            logger.info(f"Task assigned notification sent to user: {user_id}")
            return response
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}", exc_info=True)
            raise

    def post_approved_minutes(self, job: Job, approved_by: str = "", comment: str = "") -> dict:
        """
        承認された議事録をSlackに投稿（スレッド形式）
        
        メインメッセージ: タイトルのみ
        スレッド返信: 詳細情報
        
        Args:
            job: Jobモデル
            approved_by: 承認者名
            comment: コメント（任意）
            
        Returns:
            Slack APIの応答
        """
        if not self.client or not settings.SLACK_CHANNEL_ID:
            logger.warning("Slack not configured, skipping notification")
            return {"ok": False, "error": "not_configured"}
        
        try:
            # 1. メインメッセージを投稿（タイトルのみ）
            main_message_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ *議事録が承認されました*\n📄 {job.filename}"
                    }
                }
            ]
            
            main_response = self.client.chat_postMessage(
                channel=settings.SLACK_CHANNEL_ID,
                text=f"議事録が承認されました: {job.filename}",
                blocks=main_message_blocks
            )
            
            if not main_response.get("ok"):
                logger.error(f"Failed to post main message: {main_response}")
                return main_response
            
            # メインメッセージのタイムスタンプを取得（スレッド返信用）
            thread_ts = main_response["ts"]
            
            # 2. スレッド返信で詳細情報を投稿
            detail_blocks = self._build_thread_detail_blocks(job, approved_by, comment)
            
            thread_response = self.client.chat_postMessage(
                channel=settings.SLACK_CHANNEL_ID,
                text="詳細情報",
                blocks=detail_blocks,
                thread_ts=thread_ts  # スレッド返信として投稿
            )
            
            if thread_response.get("ok"):
                logger.info(f"Slack thread notification sent for job: {job.job_id}")
            else:
                logger.error(f"Failed to post thread reply: {thread_response}")
            
            # メインメッセージの応答を返す
            return main_response
            
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}", exc_info=True)
            raise

    def _build_thread_detail_blocks(self, job: Job, approved_by: str = "", comment: str = "") -> list:
        """
        スレッド返信用の詳細情報ブロックを生成
        
        Args:
            job: Jobモデル
            approved_by: 承認者名
            comment: コメント（任意）
            
        Returns:
            Slackブロックのリスト
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📋 詳細情報"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*ファイル名:*\n{job.filename}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*作成日時:*\n{job.created_at.replace(tzinfo=timezone.utc).astimezone(JST).strftime('%Y-%m-%d %H:%M')}"
                    }
                ]
            }
        ]
        
        # 承認者情報を追加
        if approved_by:
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*承認者:*\n{approved_by}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*承認日時:*\n{job.updated_at.replace(tzinfo=timezone.utc).astimezone(JST).strftime('%Y-%m-%d %H:%M') if job.updated_at else '不明'}"
                    }
                ]
            })
        
        # コメントがあれば追加
        if comment:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*コメント:*\n{comment}"
                }
            })
        
        blocks.append({
            "type": "divider"
        })
        
        # 要約を追加（スレッド内なので少し長めに）
        if job.summary:
            # 要約を3000文字に制限（スレッド内では少し長めに）
            summary_text = job.summary[:3000] + "..." if len(job.summary) > 3000 else job.summary
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*議事録要約:*\n{summary_text}"
                }
            })
        
        # Notion URLがあれば追加
        if job.notion_page_url:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📝 <{job.notion_page_url}|Notionで詳細を見る>"
                }
            })
        
        return blocks

    def _build_approved_minutes_blocks(self, job: Job, approved_by: str = "", comment: str = "") -> list:
        """
        承認済み議事録のSlackブロックを生成
        
        Args:
            job: Jobモデル
            approved_by: 承認者名
            comment: コメント（任意）
            
        Returns:
            Slackブロックのリスト
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "✅ 議事録が承認されました"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*ファイル名:*\n{job.filename}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*作成日時:*\n{job.created_at.replace(tzinfo=timezone.utc).astimezone(JST).strftime('%Y-%m-%d %H:%M')}"
                    }
                ]
            }
        ]
        
        # 承認者情報を追加
        if approved_by:
            blocks.append({
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*承認者:*\n{approved_by}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*承認日時:*\n{job.updated_at.replace(tzinfo=timezone.utc).astimezone(JST).strftime('%Y-%m-%d %H:%M') if job.updated_at else '不明'}"
                    }
                ]
            })
        
        # コメントがあれば追加
        if comment:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*コメント:*\n{comment}"
                }
            })
        
        blocks.append({
            "type": "divider"
        })
        
        # 要約を追加
        if job.summary:
            # 要約を2000文字に制限（Slackの制限）
            summary_text = job.summary[:2000] + "..." if len(job.summary) > 2000 else job.summary
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*議事録:*\n{summary_text}"
                }
            })
        
        # Notion URLがあれば追加
        if job.notion_page_url:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{job.notion_page_url}|Notionで詳細を見る>"
                }
            })
        
        return blocks


# シングルトンインスタンス
_slack_service = None


def get_slack_service() -> SlackService:
    """SlackServiceのシングルトンインスタンスを取得"""
    global _slack_service
    if _slack_service is None:
        _slack_service = SlackService()
    return _slack_service
