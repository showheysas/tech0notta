from notion_client import Client
from app.config import settings
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class NotionService:
    def __init__(self):
        self.enabled = bool(settings.NOTION_API_KEY and settings.NOTION_DATABASE_ID)
        if self.enabled:
            self.client = Client(auth=settings.NOTION_API_KEY)
            self.database_id = settings.NOTION_DATABASE_ID
            # 議事録DB ID（NOTION_DATABASE_IDを使用）
            self.meeting_database_id = settings.NOTION_DATABASE_ID
            # タスクDB ID（NOTION_TASK_DB_IDを使用）
            self.task_database_id = settings.NOTION_TASK_DB_ID
            logger.info(f"Notion integration enabled. Meeting DB: {self.meeting_database_id}, Task DB: {self.task_database_id}")
        else:
            logger.warning("Notion API key or Database ID not set. Notion integration disabled.")

    async def create_meeting_record(
        self,
        title: str,
        summary: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        議事録をNotion議事録DBに投入する
        """
        if not self.enabled:
            logger.warning("Notion integration is not configured.")
            return None
        
        try:
            metadata = metadata or {}
            
            # プロパティを構築
            properties = {
                "タイトル": {
                    "title": [
                        {
                            "text": {
                                "content": metadata.get("mtg_name") or title
                            }
                        }
                    ]
                }
            }
            
            # MTG名（テキスト）
            if metadata.get("mtg_name"):
                properties["MTG名"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": metadata["mtg_name"]
                            }
                        }
                    ]
                }
            
            # 参加者（テキスト）
            if metadata.get("participants"):
                participants_text = "、".join(metadata["participants"]) if isinstance(metadata["participants"], list) else str(metadata["participants"])
                properties["参加者"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": participants_text
                            }
                        }
                    ]
                }
            
            # 企業名（テキスト）
            if metadata.get("company_name"):
                properties["企業名"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": metadata["company_name"]
                            }
                        }
                    ]
                }
            
            # 会議日（日付）
            if metadata.get("meeting_date"):
                properties["会議日"] = {
                    "date": {
                        "start": metadata["meeting_date"]
                    }
                }
            
            # 種別（選択）
            if metadata.get("meeting_type"):
                properties["種別"] = {
                    "select": {
                        "name": metadata["meeting_type"]
                    }
                }
            
            # プロジェクト（テキスト）
            if metadata.get("project_name"):
                properties["プロジェクト"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": metadata["project_name"]
                            }
                        }
                    ]
                }
            
            # 案件名（テキスト）
            if metadata.get("project_name"):
                properties["案件名"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": metadata["project_name"]
                            }
                        }
                    ]
                }
            
            # 重要共有者（テキスト）
            if metadata.get("key_stakeholders"):
                stakeholders_text = "、".join(metadata["key_stakeholders"]) if isinstance(metadata["key_stakeholders"], list) else str(metadata["key_stakeholders"])
                properties["重要共有者"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": stakeholders_text
                            }
                        }
                    ]
                }
            
            # 重要共有チーム（選択）
            if metadata.get("key_team"):
                properties["重要共有チーム"] = {
                    "select": {
                        "name": metadata["key_team"]
                    }
                }
            
            # ナレッジ（チェックボックス）
            properties["ナレッジ"] = {
                "checkbox": metadata.get("is_knowledge", False)
            }
            
            # 資料（URL）
            if metadata.get("materials_url"):
                properties["資料"] = {
                    "url": metadata["materials_url"]
                }
            
            # 備考（テキスト）
            if metadata.get("notes"):
                properties["備考"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": metadata["notes"]
                            }
                        }
                    ]
                }
            
            # 検索ワード（テキスト）
            if metadata.get("search_keywords"):
                properties["検索ワード"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": metadata["search_keywords"]
                            }
                        }
                    ]
                }
            
            # ページコンテンツを構築
            children = self._build_meeting_content(summary, metadata)
            
            # Notionページを作成
            response = self.client.pages.create(
                parent={"database_id": self.meeting_database_id},
                properties=properties,
                children=children
            )
            
            page_id = response["id"]
            page_url = response["url"]
            
            logger.info(f"Meeting record created in Notion: {page_id}")
            
            return {
                "id": page_id,
                "url": page_url
            }
            
        except Exception as e:
            logger.error(f"Error creating meeting record in Notion: {e}")
            raise

    async def update_meeting_tasks_relation(
        self,
        meeting_page_id: str,
        task_ids: List[str]
    ) -> None:
        """
        議事録ページの「タスク」リレーションを更新する
        """
        if not self.enabled:
            logger.warning("Notion integration is not configured.")
            return
        
        try:
            task_relations = [{"id": task_id} for task_id in task_ids]
            
            self.client.pages.update(
                page_id=meeting_page_id,
                properties={
                    "タスク": {
                        "relation": task_relations
                    }
                }
            )
            
            logger.info(f"Updated meeting {meeting_page_id} with {len(task_ids)} task relations")
            
        except Exception as e:
            logger.error(f"Error updating meeting tasks relation: {e}")
            raise
    
    def _build_meeting_content(self, summary: str, metadata: Dict[str, Any]) -> list:
        """議事録ページのコンテンツを構築"""
        children = []
        
        # 参加者セクション
        participants = metadata.get("participants", [])
        if participants:
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "参加者"}}]
                }
            })
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": "、".join(participants)}}]
                }
            })
        
        # 要約セクション
        summary_sections = self._parse_summary(summary)
        
        for section_title in ["概要", "主な議題", "決定事項", "アクションアイテム", "次回の議題"]:
            if section_title in summary_sections:
                children.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": section_title}}]
                    }
                })
                
                content = summary_sections[section_title]
                if len(content) > 2000:
                    for i in range(0, len(content), 2000):
                        children.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": content[i:i+2000]}}]
                            }
                        })
                else:
                    children.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": content}}]
                        }
                    })
        
        return children

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
                    "名前": {
                        "title": [
                            {
                                "text": {
                                    "content": title
                                }
                            }
                        ]
                    },
                    # "日付": {
                    #     "date": {
                    #         "start": datetime.now().isoformat()
                    #     }
                    # },
                    # "音声ファイル": {
                    #     "rich_text": [
                    #         {
                    #             "text": {
                    #                 "content": audio_filename
                    #             }
                    #         }
                    #     ]
                    # }
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


def get_notion_client() -> NotionService:
    """get_notion_serviceのエイリアス"""
    return get_notion_service()
