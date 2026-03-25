"""Notion 議事録 CRUD 操作"""
import logging
from typing import Optional

from app.services.notion.base import NotionServiceBase
from app.services.notion.content_builder import (
    build_meeting_content,
    content_to_blocks,
    parse_summary,
)

logger = logging.getLogger(__name__)


class NotionMeetingService(NotionServiceBase):
    """議事録の作成・更新を担当するサービス"""

    async def create_meeting_record(
        self,
        title: str,
        summary: str,
        metadata: Optional[dict] = None
    ) -> Optional[dict]:
        """議事録をNotion議事録DBに投入する"""
        if not self.enabled:
            logger.warning("Notion integration is not configured.")
            return None

        try:
            metadata = metadata or {}

            properties = {
                "タイトル": {
                    "title": [{"text": {"content": metadata.get("mtg_name") or title}}]
                }
            }

            if metadata.get("mtg_name"):
                properties["MTG名"] = {
                    "rich_text": [{"text": {"content": metadata["mtg_name"]}}]
                }

            if metadata.get("participants"):
                participants_text = (
                    "、".join(metadata["participants"])
                    if isinstance(metadata["participants"], list)
                    else str(metadata["participants"])
                )
                properties["参加者"] = {
                    "rich_text": [{"text": {"content": participants_text}}]
                }

            if metadata.get("company_name"):
                properties["企業名"] = {
                    "rich_text": [{"text": {"content": metadata["company_name"]}}]
                }

            if metadata.get("meeting_date"):
                properties["会議日"] = {"date": {"start": metadata["meeting_date"]}}

            if metadata.get("meeting_type"):
                properties["種別"] = {"select": {"name": metadata["meeting_type"]}}

            if metadata.get("project_name"):
                properties["プロジェクト"] = {
                    "rich_text": [{"text": {"content": metadata["project_name"]}}]
                }

            if metadata.get("project_name"):
                properties["案件名"] = {
                    "rich_text": [{"text": {"content": metadata["project_name"]}}]
                }

            if metadata.get("key_stakeholders"):
                stakeholders_text = (
                    "、".join(metadata["key_stakeholders"])
                    if isinstance(metadata["key_stakeholders"], list)
                    else str(metadata["key_stakeholders"])
                )
                properties["重要共有者"] = {
                    "rich_text": [{"text": {"content": stakeholders_text}}]
                }

            if metadata.get("key_team"):
                properties["重要共有チーム"] = {"select": {"name": metadata["key_team"]}}

            properties["ナレッジ"] = {"checkbox": metadata.get("is_knowledge", False)}

            if metadata.get("materials_url"):
                properties["資料"] = {"url": metadata["materials_url"]}

            if metadata.get("notes"):
                properties["備考"] = {
                    "rich_text": [{"text": {"content": metadata["notes"]}}]
                }

            if metadata.get("search_keywords"):
                properties["検索ワード"] = {
                    "rich_text": [{"text": {"content": metadata["search_keywords"]}}]
                }

            children = build_meeting_content(summary, metadata)

            response = self.client.pages.create(
                parent={"database_id": self.meeting_database_id},
                properties=properties,
                children=children
            )

            page_id = response["id"]
            page_url = response["url"]

            logger.info(f"Meeting record created in Notion: {page_id}")

            return {"id": page_id, "url": page_url}

        except Exception as e:
            logger.error(f"Error creating meeting record in Notion: {e}", exc_info=True)
            raise

    async def update_meeting_tasks_relation(
        self,
        meeting_page_id: str,
        task_ids: list[str]
    ) -> None:
        """議事録ページの「タスク」リレーションを更新する"""
        if not self.enabled:
            logger.warning("Notion integration is not configured.")
            return

        try:
            task_relations = [{"id": task_id} for task_id in task_ids]

            self.client.pages.update(
                page_id=meeting_page_id,
                properties={"タスク": {"relation": task_relations}}
            )

            logger.info(f"Updated meeting {meeting_page_id} with {len(task_ids)} task relations")

        except Exception as e:
            logger.error(f"Error updating meeting tasks relation: {e}", exc_info=True)
            raise

    async def update_meeting_project_relation(
        self,
        meeting_page_id: str,
        project_page_id: str
    ) -> None:
        """議事録ページの「案件」リレーションを更新する"""
        if not self.enabled:
            logger.warning("Notion integration is not configured.")
            return

        try:
            self.client.pages.update(
                page_id=meeting_page_id,
                properties={"案件": {"relation": [{"id": project_page_id}]}}
            )

            logger.info(f"Updated meeting {meeting_page_id} with project relation {project_page_id}")

        except Exception as e:
            logger.error(f"Error updating meeting project relation: {e}", exc_info=True)
            raise

    def create_meeting_note(
        self,
        title: str,
        transcription: str,
        summary: str,
        audio_filename: str
    ) -> tuple[str, str]:
        """レガシー: 議事録ページを作成する（旧 notion.py ルーターから呼ばれる）"""
        if not self.enabled:
            raise Exception("Notion integration is not configured. Set NOTION_API_KEY and NOTION_DATABASE_ID.")
        try:
            summary_sections = parse_summary(summary)

            children = []
            for section_title, content in summary_sections.items():
                children.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": section_title}}]
                    }
                })
                content_blocks = content_to_blocks(content)
                children.extend(content_blocks)

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
                    "名前": {
                        "title": [{"text": {"content": title}}]
                    },
                },
                children=children
            )

            page_id = response["id"]
            page_url = response["url"]
            logger.info(f"Notion page created: {page_id}")
            return page_id, page_url

        except Exception as e:
            logger.error(f"Error creating Notion page: {e}", exc_info=True)
            raise
