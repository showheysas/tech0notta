from notion_client import Client
from app.config import settings
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class NotionService:
    def __init__(self):
        self.enabled = bool(settings.NOTION_API_KEY and settings.NOTION_DATABASE_ID)
        if self.enabled:
            self.client = Client(auth=settings.NOTION_API_KEY)
            self.database_id = settings.NOTION_DATABASE_ID
        else:
            logger.warning("Notion API key or Database ID not set. Notion integration disabled.")

    def create_meeting_note(
        self,
        title: str,
        transcription: str,
        summary: str,
        audio_filename: str
    ) -> tuple[str, str]:
        if not self.enabled:
            raise Exception("Notion integration is not configured. Set NOTION_API_KEY and NOTION_DATABASE_ID.")
        try:
            summary_sections = self._parse_summary(summary)

            children = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "概要"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": summary_sections.get("概要", "")}}]
                    }
                }
            ]

            for section_title in ["主な議題", "決定事項", "アクションアイテム", "次回の議題"]:
                if section_title in summary_sections:
                    children.append({
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": section_title}}]
                        }
                    })
                    children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": summary_sections[section_title]}}]
                        }
                    })

            children.extend([
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "全文書き起こし"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": "書き起こしテキストを表示"}}],
                        "children": [
                            {
                                "object": "block",
                                "type": "paragraph",
                                "paragraph": {
                                    "rich_text": [{"type": "text", "text": {"content": transcription[:2000]}}]
                                }
                            }
                        ]
                    }
                }
            ])

            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties={
                    "Name": {
                        "title": [
                            {
                                "text": {
                                    "content": title
                                }
                            }
                        ]
                    },
                    "日付": {
                        "date": {
                            "start": datetime.now().isoformat()
                        }
                    },
                    "音声ファイル": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": audio_filename
                                }
                            }
                        ]
                    }
                },
                children=children
            )

            page_id = response["id"]
            page_url = response["url"]
            logger.info(f"Notion page created: {page_id}")
            return page_id, page_url

        except Exception as e:
            logger.error(f"Error creating Notion page: {e}")
            raise

    def _parse_summary(self, summary: str) -> dict:
        sections = {}
        current_section = None
        current_content = []

        for line in summary.split("\n"):
            line = line.strip()
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = line[3:].strip()
                current_content = []
            elif line and current_section:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections


_notion_service = None


def get_notion_service() -> NotionService:
    global _notion_service
    if _notion_service is None:
        _notion_service = NotionService()
    return _notion_service
