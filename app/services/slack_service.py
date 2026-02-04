from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from app.config import settings
from app.models.job import Job
import logging

logger = logging.getLogger(__name__)


class SlackService:
    """Slack通知サービス"""
    
    def __init__(self):
        if settings.SLACK_BOT_TOKEN:
            self.client = WebClient(token=settings.SLACK_BOT_TOKEN)
        else:
            self.client = None
            logger.warning("SLACK_BOT_TOKEN not configured")
    
    def post_approved_minutes(self, job: Job, approved_by: str = "", comment: str = "") -> dict:
        """
        承認された議事録をSlackに投稿
        
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
        
        blocks = self._build_approved_minutes_blocks(job, approved_by, comment)
        
        try:
            response = self.client.chat_postMessage(
                channel=settings.SLACK_CHANNEL_ID,
                text=f"議事録が承認されました: {job.filename}",
                blocks=blocks
            )
            logger.info(f"Slack notification sent for job: {job.job_id}")
            return response
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}")
            raise
    
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
                        "text": f"*作成日時:*\n{job.created_at.strftime('%Y-%m-%d %H:%M')}"
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
                        "text": f"*承認日時:*\n{job.updated_at.strftime('%Y-%m-%d %H:%M') if job.updated_at else '不明'}"
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
