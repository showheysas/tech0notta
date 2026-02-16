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
            # 案件DB ID（NOTION_PROJECT_DB_IDを使用）
            self.project_database_id = settings.NOTION_PROJECT_DB_ID
            logger.info(f"Notion integration enabled. Meeting DB: {self.meeting_database_id}, Task DB: {self.task_database_id}, Project DB: {self.project_database_id}")
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

    async def update_meeting_project_relation(
        self,
        meeting_page_id: str,
        project_page_id: str
    ) -> None:
        """
        議事録ページの「案件」リレーションを更新する
        """
        if not self.enabled:
            logger.warning("Notion integration is not configured.")
            return
        
        try:
            self.client.pages.update(
                page_id=meeting_page_id,
                properties={
                    "案件": {
                        "relation": [{"id": project_page_id}]
                    }
                }
            )
            
            logger.info(f"Updated meeting {meeting_page_id} with project relation {project_page_id}")
            
        except Exception as e:
            logger.error(f"Error updating meeting project relation: {e}")
            raise

    # --- 案件DB操作 ---

    async def list_projects(self) -> List[Dict[str, Any]]:
        """
        Notion案件DBから案件一覧を取得する
        """
        if not self.enabled or not self.project_database_id:
            logger.warning("Project DB is not configured.")
            return []
        
        try:
            results = self.client.databases.query(
                database_id=self.project_database_id,
                sorts=[{"property": "案件名", "direction": "ascending"}]
            )
            
            projects = []
            for page in results.get("results", []):
                props = page.get("properties", {})
                project = {
                    "id": page["id"],
                    "url": page.get("url", ""),
                }
                
                # 案件名（タイトル）
                title_prop = props.get("案件名", {})
                if title_prop.get("title"):
                    project["name"] = "".join(
                        t.get("plain_text", "") for t in title_prop["title"]
                    )
                else:
                    project["name"] = ""
                
                # ステータス（選択）
                status_prop = props.get("ステータス", {})
                if status_prop.get("select"):
                    project["status"] = status_prop["select"].get("name", "")
                else:
                    project["status"] = ""
                
                # 重要度（選択）
                importance_prop = props.get("重要度", {})
                if importance_prop.get("select"):
                    project["importance"] = importance_prop["select"].get("name", "")
                else:
                    project["importance"] = ""
                
                # 企業名（リレーション or テキスト）
                company_prop = props.get("企業名", {})
                if company_prop.get("relation"):
                    # リレーションの場合はIDのみ取得
                    project["company_ids"] = [r["id"] for r in company_prop["relation"]]
                elif company_prop.get("rich_text"):
                    project["company_name"] = "".join(
                        t.get("plain_text", "") for t in company_prop["rich_text"]
                    )
                
                # 受注金額（数値）
                amount_prop = props.get("受注金額", {})
                if amount_prop.get("number") is not None:
                    project["amount"] = amount_prop["number"]
                
                # 受注時期目安（日付）
                close_date_prop = props.get("受注時期目安", {})
                if close_date_prop.get("date"):
                    project["expected_close_date"] = close_date_prop["date"].get("start", "")
                
                # 案件開始日（日付）
                start_prop = props.get("案件開始日", {})
                if start_prop.get("date"):
                    project["start_date"] = start_prop["date"].get("start", "")
                
                # 案件終了日（日付）
                end_prop = props.get("案件終了日", {})
                if end_prop.get("date"):
                    project["end_date"] = end_prop["date"].get("start", "")
                
                projects.append(project)
            
            logger.info(f"Listed {len(projects)} projects from Notion")
            return projects
            
        except Exception as e:
            logger.error(f"Error listing projects from Notion: {e}")
            raise

    async def create_project_record(
        self,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Notion案件DBに案件レコードを作成する
        
        data keys:
            name: 案件名（必須）
            status: ステータス
            importance: 重要度
            situation: 状況
            company_name: 企業名（テキスト）
            department: 部署名
            amount: 受注金額
            expected_close_date: 受注時期目安
            director: ディレクター
            pdm: PdM
            biz: Biz
            tech: Tech
            design: Design
            start_date: 案件開始日
            end_date: 案件終了日
            dropbox_url: DropBoxURL
        """
        if not self.enabled or not self.project_database_id:
            logger.warning("Project DB is not configured.")
            return None
        
        try:
            properties = {
                "案件名": {
                    "title": [{"text": {"content": data.get("name", "")}}]
                }
            }
            
            # ステータス（選択）
            if data.get("status"):
                properties["ステータス"] = {"select": {"name": data["status"]}}
            
            # 重要度（選択）
            if data.get("importance"):
                properties["重要度"] = {"select": {"name": data["importance"]}}
            
            # 状況（選択）
            if data.get("situation"):
                properties["状況"] = {"select": {"name": data["situation"]}}
            
            # 部署名（テキスト）
            if data.get("department"):
                properties["部署名"] = {
                    "rich_text": [{"text": {"content": data["department"]}}]
                }
            
            # 受注金額（数値）
            if data.get("amount") is not None:
                properties["受注金額"] = {"number": data["amount"]}
            
            # 受注時期目安（日付）
            if data.get("expected_close_date"):
                properties["受注時期目安"] = {"date": {"start": data["expected_close_date"]}}
            
            # ロール系（複数選択 or テキスト）
            for role_key, prop_name in [
                ("director", "ディレクター"),
                ("pdm", "PdM"),
                ("biz", "Biz"),
                ("tech", "Tech"),
                ("design", "Design"),
            ]:
                if data.get(role_key):
                    val = data[role_key]
                    if isinstance(val, list):
                        text = "、".join(val)
                    else:
                        text = str(val)
                    properties[prop_name] = {
                        "rich_text": [{"text": {"content": text}}]
                    }
            
            # 案件開始日（日付）
            if data.get("start_date"):
                properties["案件開始日"] = {"date": {"start": data["start_date"]}}
            
            # 案件終了日（日付）
            if data.get("end_date"):
                properties["案件終了日"] = {"date": {"start": data["end_date"]}}
            
            # DropBoxURL（URL or テキスト）
            if data.get("dropbox_url"):
                properties["DropBoxURL"] = {"url": data["dropbox_url"]}
            
            response = self.client.pages.create(
                parent={"database_id": self.project_database_id},
                properties=properties
            )
            
            page_id = response["id"]
            page_url = response["url"]
            
            logger.info(f"Project record created in Notion: {page_id}")
            
            return {
                "id": page_id,
                "url": page_url,
                "name": data.get("name", "")
            }
            
        except Exception as e:
            logger.error(f"Error creating project record in Notion: {e}")
            raise
    
    def _build_meeting_content(self, summary: str, metadata: Dict[str, Any]) -> list:
        """議事録ページのコンテンツを構築（新フォーマット対応・テーブル変換あり）"""
        children = []
        
        # 参加者セクション（メタデータから）
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
        
        # 要約全文をセクションごとにNotionブロックとして構築
        sections = self._parse_summary(summary)
        
        for section_title, content in sections.items():
            # セクション見出し
            children.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": section_title}}]
                }
            })
            
            # コンテンツをテーブルとテキストに分離してブロック化
            content_blocks = self._content_to_blocks(content)
            children.extend(content_blocks)
        
        return children

    def _content_to_blocks(self, content: str) -> list:
        """
        セクション内容をNotionブロックのリストに変換する。
        Markdownテーブルを検出したらNotion tableブロックに変換し、
        それ以外はparagraphブロックにする。
        """
        blocks = []
        lines = content.split("\n")
        i = 0
        text_buffer = []
        
        while i < len(lines):
            line = lines[i]
            
            # Markdownテーブルの開始を検出（| で始まり | で終わる行）
            if line.strip().startswith("|") and line.strip().endswith("|"):
                # バッファに溜まったテキストを先にflush
                if text_buffer:
                    self._flush_text_buffer(text_buffer, blocks)
                    text_buffer = []
                
                # テーブル行を収集
                table_lines = []
                while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                    table_lines.append(lines[i].strip())
                    i += 1
                
                # テーブルブロックに変換
                table_block = self._markdown_table_to_notion(table_lines)
                if table_block:
                    blocks.append(table_block)
            else:
                text_buffer.append(line)
                i += 1
        
        # 残りのテキストをflush
        if text_buffer:
            self._flush_text_buffer(text_buffer, blocks)
        
        return blocks

    def _flush_text_buffer(self, text_buffer: list, blocks: list):
        """テキストバッファをparagraphブロックとしてflush"""
        text = "\n".join(text_buffer).strip()
        if not text:
            return
        # 2000文字制限対応
        if len(text) > 2000:
            for j in range(0, len(text), 2000):
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": text[j:j+2000]}}]
                    }
                })
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": text}}]
                }
            })

    def _markdown_table_to_notion(self, table_lines: list) -> Optional[dict]:
        """
        Markdownテーブル行のリストをNotion APIのtableブロックに変換する。
        
        入力例:
            ["| トピック | 内容 | 決定事項 |",
             "|---------|------|---------|",
             "| **項目A** | 詳細 | 決定 |"]
        """
        if len(table_lines) < 2:
            return None
        
        # 各行をセルに分割
        rows = []
        for line in table_lines:
            # 区切り行（|---|---|---| のような行）はスキップ
            stripped = line.strip().strip("|").strip()
            if all(c in "-| :" for c in stripped):
                continue
            
            # セルに分割
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows.append(cells)
        
        if not rows:
            return None
        
        # 列数を統一（最大列数に合わせる）
        max_cols = max(len(row) for row in rows)
        
        # Notion tableブロックを構築
        table_rows = []
        for row in rows:
            # 列数を揃える
            while len(row) < max_cols:
                row.append("")
            
            cells = []
            for cell_text in row[:max_cols]:
                # **太字** をrich_textのboldに変換
                rich_texts = self._parse_cell_rich_text(cell_text)
                cells.append(rich_texts)
            
            table_rows.append({
                "object": "block",
                "type": "table_row",
                "table_row": {
                    "cells": cells
                }
            })
        
        return {
            "object": "block",
            "type": "table",
            "table": {
                "table_width": max_cols,
                "has_column_header": True,  # 1行目をヘッダーとして扱う
                "has_row_header": False,
                "children": table_rows
            }
        }

    def _parse_cell_rich_text(self, text: str) -> list:
        """
        セルテキストをNotion rich_textに変換する。
        **太字** をboldアノテーションに変換。
        <br> を改行に変換。
        """
        import re
        
        # <br> / <br/> を改行に変換
        text = re.sub(r'<br\s*/?>', '\n', text)
        
        result = []
        # **太字** パターンを分割
        parts = re.split(r'(\*\*[^*]+\*\*)', text)
        
        for part in parts:
            if not part:
                continue
            if part.startswith("**") and part.endswith("**"):
                # 太字
                result.append({
                    "type": "text",
                    "text": {"content": part[2:-2]},
                    "annotations": {"bold": True}
                })
            else:
                result.append({
                    "type": "text",
                    "text": {"content": part}
                })
        
        if not result:
            result.append({"type": "text", "text": {"content": ""}})
        
        return result

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

            children = []

            # 全セクションを動的に追加（新旧フォーマット両対応・テーブル変換あり）
            for section_title, content in summary_sections.items():
                children.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": section_title}}]
                    }
                })
                content_blocks = self._content_to_blocks(content)
                children.extend(content_blocks)

            # 全文書き起こし（トグル）
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
        """
        要約テキストを ## / ### ヘッダーでセクション分割する。
        新フォーマット（アジェンダ、詳細論点、ネクストアクション、参加者別質問）と
        旧フォーマット（概要、主な議題、決定事項、アクションアイテム、次回の議題）の
        両方に対応する。
        """
        sections = {}
        current_section = None
        current_content = []

        for line in summary.split("\n"):
            stripped = line.strip()
            # ## または ### で始まるヘッダーをセクション区切りとして扱う
            if stripped.startswith("## ") or stripped.startswith("### "):
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                # ヘッダーのプレフィックスを除去
                if stripped.startswith("### "):
                    current_section = stripped[4:].strip()
                else:
                    current_section = stripped[3:].strip()
                current_content = []
            elif current_section is not None:
                # 空行も保持（テーブルの整形に必要）
                current_content.append(line.rstrip())

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
