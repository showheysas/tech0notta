
import logging
from datetime import datetime
from notion_client import AsyncClient
from app.zoom_notion_config import notion_settings

logger = logging.getLogger(__name__)

class ZoomNotionService:
    """Zoom用Notion同期サービス（既存のnotion_client.pyとは別管理）"""
    
    def __init__(self):
        self.api_key = notion_settings.NOTION_API_KEY
        self.database_id = notion_settings.NOTION_DATABASE_ID
        
        if not self.api_key:
            logger.warning("NOTION_API_KEY is not set. Notion integration will be disabled.")
            self.client = None
        else:
            self.client = AsyncClient(auth=self.api_key)

    async def create_meeting_note(self, title: str, summary: str, tags: list[str]) -> dict:
        """
        Notionデータベースに議事録ページを作成する
        
        Args:
            title (str): 会議タイトル
            summary (str): エグゼクティブサマリー
            tags (list[str]): インサイトタグ
            
        Returns:
            dict: 作成されたページの情報
        """
        if not self.client:
            raise ValueError("Notion API Key is not configured")

        if not self.database_id:
            raise ValueError("Notion Database ID is not configured")

        try:
            # プロパティの構築
            # ユーザー提供の画像に基づくマッピング:
            # - 会議日: date
            # - 検索ワード: rich_text (タグを文字列化)
            # - 備考: rich_text (サマリー)
            # - Name (デフォルト): title (会議名)
            
            # タグを文字列に変換（例: "#開発 #ミーティング"）
            tags_str = " ".join([f"#{tag}" for tag in tags])
            
            properties = {
                # タイトルプロパティ（名前が不明なためデフォルトの'Name'または'名前'を想定）
                # 通常Notionで作成したDBのタイトル列は 'Name' か '名前' です
                "名前": {  # もしエラーになる場合はここを修正してください（例: "企業名" など）
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "会議日": {
                    "date": {
                        "start": datetime.now().date().isoformat()
                    }
                },
                "検索ワード": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": tags_str
                            }
                        }
                    ]
                },
                "備考": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": summary[:2000] # 長すぎるとエラーになる可能性があるため制限
                            }
                        }
                    ]
                }
            }
            
            # ページ本文としてのブロック
            children = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "Executive Summary"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": summary
                                }
                            }
                        ]
                    }
                }
            ]

            response = await self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=children
            )
            
            logger.info(f"Successfully created Notion page: {response.get('url')}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to create Notion page: {e}")
            raise e

zoom_notion_service = ZoomNotionService()
