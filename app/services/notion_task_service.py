"""
Notion Task Service - Notion Task DBとの連携を担当

タスクの作成、更新、削除、取得を行います。
リトライ処理（3回、指数バックオフ）を実装しています。
"""
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from notion_client import Client, APIResponseError
from app.config import settings
from app.models.task import TaskStatus, TaskPriority
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import logging

logger = logging.getLogger(__name__)


class NotionTaskService:
    """Notion Task DB連携サービス"""

    def __init__(self):
        self.enabled = bool(settings.NOTION_API_KEY and settings.NOTION_TASK_DB_ID)
        if self.enabled:
            self.client = Client(auth=settings.NOTION_API_KEY)
            self.task_db_id = settings.NOTION_TASK_DB_ID
            logger.info("Notion Task Service initialized")
        else:
            logger.warning(
                "Notion API key or Task DB ID not set. Task registration disabled."
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(APIResponseError),
        reraise=True
    )
    async def create_task(
        self,
        title: str,
        description: Optional[str],
        assignee: Optional[str],
        due_date: date,
        priority: TaskPriority,
        status: TaskStatus,
        project_id: str,
        meeting_id: str,
        parent_task_id: Optional[str] = None
    ) -> str:
        """
        Notion Task DBにタスクを作成する

        Args:
            title: タスク名
            description: 詳細説明
            assignee: 担当者
            due_date: 期限
            priority: 優先度
            status: ステータス
            project_id: プロジェクトID（Notion Page ID）
            meeting_id: 議事録ID（Job ID）
            parent_task_id: 親タスクID（サブタスクの場合）

        Returns:
            作成されたタスクのNotion Page ID

        Raises:
            APIResponseError: Notion APIエラー（リトライ後も失敗した場合）
        """
        if not self.enabled:
            raise Exception(
                "Notion Task integration is not configured. "
                "Set NOTION_API_KEY and NOTION_TASK_DB_ID."
            )

        try:
            # タスクプロパティを構築
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "Due Date": {
                    "date": {
                        "start": due_date.isoformat()
                    }
                },
                "Status": {
                    "select": {
                        "name": status.value
                    }
                },
                "Priority": {
                    "select": {
                        "name": priority.value
                    }
                }
            }

            # 担当者が指定されている場合（"未割り当て"以外）
            # Note: Notion APIでPeopleプロパティを設定するには、
            # ユーザーIDが必要です。ここでは担当者名をRich Textとして保存します。
            if assignee and assignee != "未割り当て":
                properties["Assignee"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": assignee
                            }
                        }
                    ]
                }

            # プロジェクトリレーション
            if project_id:
                properties["Project"] = {
                    "relation": [
                        {
                            "id": project_id
                        }
                    ]
                }

            # 議事録リレーション
            if meeting_id:
                properties["Meeting"] = {
                    "relation": [
                        {
                            "id": meeting_id
                        }
                    ]
                }

            # 親タスクリレーション（サブタスクの場合）
            if parent_task_id:
                properties["Parent Task"] = {
                    "relation": [
                        {
                            "id": parent_task_id
                        }
                    ]
                }

            # 詳細説明をページコンテンツとして追加
            children = []
            if description:
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": description
                                }
                            }
                        ]
                    }
                })

            # Notion APIでページを作成
            response = self.client.pages.create(
                parent={"database_id": self.task_db_id},
                properties=properties,
                children=children if children else None
            )

            task_id = response["id"]
            logger.info(f"Created task in Notion: {task_id} - {title}")
            return task_id

        except APIResponseError as e:
            logger.error(f"Notion API error creating task: {e.status} - {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error creating task in Notion: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(APIResponseError),
        reraise=True
    )
    async def query_tasks(
        self,
        project_id: Optional[str] = None,
        assignee: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        due_date_from: Optional[date] = None,
        due_date_to: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Notion Task DBからタスクを検索する

        Args:
            project_id: プロジェクトIDでフィルター
            assignee: 担当者でフィルター
            status: ステータスでフィルター
            priority: 優先度でフィルター
            due_date_from: 期限開始日でフィルター
            due_date_to: 期限終了日でフィルター

        Returns:
            タスクのリスト（Notion APIレスポンス形式）

        Raises:
            APIResponseError: Notion APIエラー（リトライ後も失敗した場合）
        """
        if not self.enabled:
            raise Exception(
                "Notion Task integration is not configured. "
                "Set NOTION_API_KEY and NOTION_TASK_DB_ID."
            )

        try:
            # フィルター条件を構築
            filters = []

            if project_id:
                filters.append({
                    "property": "Project",
                    "relation": {
                        "contains": project_id
                    }
                })

            if assignee:
                filters.append({
                    "property": "Assignee",
                    "rich_text": {
                        "contains": assignee
                    }
                })

            if status:
                filters.append({
                    "property": "Status",
                    "select": {
                        "equals": status.value
                    }
                })

            if priority:
                filters.append({
                    "property": "Priority",
                    "select": {
                        "equals": priority.value
                    }
                })

            if due_date_from:
                filters.append({
                    "property": "Due Date",
                    "date": {
                        "on_or_after": due_date_from.isoformat()
                    }
                })

            if due_date_to:
                filters.append({
                    "property": "Due Date",
                    "date": {
                        "on_or_before": due_date_to.isoformat()
                    }
                })

            # クエリを構築
            query_params = {
                "database_id": self.task_db_id
            }

            if filters:
                if len(filters) == 1:
                    query_params["filter"] = filters[0]
                else:
                    query_params["filter"] = {
                        "and": filters
                    }

            # Notion APIでクエリを実行
            response = self.client.databases.query(**query_params)
            
            logger.info(f"Queried {len(response['results'])} tasks from Notion")
            return response["results"]

        except APIResponseError as e:
            logger.error(f"Notion API error querying tasks: {e.status} - {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error querying tasks from Notion: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(APIResponseError),
        reraise=True
    )
    async def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        Notion Task DBから特定のタスクを取得する

        Args:
            task_id: タスクID（Notion Page ID）

        Returns:
            タスク情報（Notion APIレスポンス形式）

        Raises:
            APIResponseError: Notion APIエラー（リトライ後も失敗した場合）
        """
        if not self.enabled:
            raise Exception(
                "Notion Task integration is not configured. "
                "Set NOTION_API_KEY and NOTION_TASK_DB_ID."
            )

        try:
            response = self.client.pages.retrieve(page_id=task_id)
            logger.info(f"Retrieved task from Notion: {task_id}")
            return response

        except APIResponseError as e:
            logger.error(f"Notion API error retrieving task: {e.status} - {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error retrieving task from Notion: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(APIResponseError),
        reraise=True
    )
    async def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        assignee: Optional[str] = None,
        due_date: Optional[date] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        completion_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Notion Task DBのタスクを更新する

        Args:
            task_id: タスクID（Notion Page ID）
            title: タスク名
            description: 詳細説明
            assignee: 担当者
            due_date: 期限
            status: ステータス
            priority: 優先度
            completion_date: 完了日

        Returns:
            更新されたタスク情報（Notion APIレスポンス形式）

        Raises:
            APIResponseError: Notion APIエラー（リトライ後も失敗した場合）
        """
        if not self.enabled:
            raise Exception(
                "Notion Task integration is not configured. "
                "Set NOTION_API_KEY and NOTION_TASK_DB_ID."
            )

        try:
            # 更新するプロパティを構築
            properties = {}

            if title is not None:
                properties["Name"] = {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }

            if assignee is not None:
                if assignee and assignee != "未割り当て":
                    properties["Assignee"] = {
                        "rich_text": [
                            {
                                "text": {
                                    "content": assignee
                                }
                            }
                        ]
                    }
                else:
                    # 担当者をクリア
                    properties["Assignee"] = {
                        "rich_text": []
                    }

            if due_date is not None:
                properties["Due Date"] = {
                    "date": {
                        "start": due_date.isoformat()
                    }
                }

            if status is not None:
                properties["Status"] = {
                    "select": {
                        "name": status.value
                    }
                }

            if priority is not None:
                properties["Priority"] = {
                    "select": {
                        "name": priority.value
                    }
                }

            if completion_date is not None:
                properties["Completion Date"] = {
                    "date": {
                        "start": completion_date.isoformat()
                    }
                }

            # Notion APIでページを更新
            response = self.client.pages.update(
                page_id=task_id,
                properties=properties
            )

            logger.info(f"Updated task in Notion: {task_id}")
            return response

        except APIResponseError as e:
            logger.error(f"Notion API error updating task: {e.status} - {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error updating task in Notion: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(APIResponseError),
        reraise=True
    )
    async def delete_task(self, task_id: str) -> None:
        """
        Notion Task DBからタスクを削除する（アーカイブ）

        Args:
            task_id: タスクID（Notion Page ID）

        Raises:
            APIResponseError: Notion APIエラー（リトライ後も失敗した場合）
        """
        if not self.enabled:
            raise Exception(
                "Notion Task integration is not configured. "
                "Set NOTION_API_KEY and NOTION_TASK_DB_ID."
            )

        try:
            # Notionではページを削除ではなくアーカイブする
            self.client.pages.update(
                page_id=task_id,
                archived=True
            )

            logger.info(f"Archived task in Notion: {task_id}")

        except APIResponseError as e:
            logger.error(f"Notion API error archiving task: {e.status} - {e.message}")
            raise
        except Exception as e:
            logger.error(f"Error archiving task in Notion: {e}")
            raise

    def parse_task_response(self, notion_page: Dict[str, Any]) -> Dict[str, Any]:
        """
        Notion APIレスポンスからタスク情報を抽出する

        Args:
            notion_page: Notion APIのページレスポンス

        Returns:
            パースされたタスク情報
        """
        properties = notion_page.get("properties", {})
        
        # タイトルを取得
        title = ""
        if "Name" in properties and properties["Name"]["title"]:
            title = properties["Name"]["title"][0]["text"]["content"]
        
        # 担当者を取得
        assignee = None
        if "Assignee" in properties and properties["Assignee"]["rich_text"]:
            assignee = properties["Assignee"]["rich_text"][0]["text"]["content"]
        
        # 期限を取得
        due_date = None
        if "Due Date" in properties and properties["Due Date"]["date"]:
            due_date_str = properties["Due Date"]["date"]["start"]
            due_date = date.fromisoformat(due_date_str)
        
        # ステータスを取得
        status = TaskStatus.NOT_STARTED
        if "Status" in properties and properties["Status"]["select"]:
            status_name = properties["Status"]["select"]["name"]
            status = TaskStatus(status_name)
        
        # 優先度を取得
        priority = TaskPriority.MEDIUM
        if "Priority" in properties and properties["Priority"]["select"]:
            priority_name = properties["Priority"]["select"]["name"]
            priority = TaskPriority(priority_name)
        
        # プロジェクトIDを取得
        project_id = None
        if "Project" in properties and properties["Project"]["relation"]:
            project_id = properties["Project"]["relation"][0]["id"]
        
        # 議事録IDを取得
        meeting_id = None
        if "Meeting" in properties and properties["Meeting"]["relation"]:
            meeting_id = properties["Meeting"]["relation"][0]["id"]
        
        # 親タスクIDを取得
        parent_task_id = None
        if "Parent Task" in properties and properties["Parent Task"]["relation"]:
            parent_task_id = properties["Parent Task"]["relation"][0]["id"]
        
        # 完了日を取得
        completion_date = None
        if "Completion Date" in properties and properties["Completion Date"]["date"]:
            completion_date_str = properties["Completion Date"]["date"]["start"]
            completion_date = date.fromisoformat(completion_date_str)
        
        # 作成日時・更新日時を取得
        created_at = datetime.fromisoformat(notion_page["created_time"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(notion_page["last_edited_time"].replace("Z", "+00:00"))
        
        # Notion URLを取得
        notion_page_url = notion_page.get("url", "")
        
        return {
            "id": notion_page["id"],
            "title": title,
            "assignee": assignee,
            "due_date": due_date,
            "status": status,
            "priority": priority,
            "project_id": project_id,
            "meeting_id": meeting_id,
            "parent_task_id": parent_task_id,
            "completion_date": completion_date,
            "notion_page_url": notion_page_url,
            "created_at": created_at,
            "updated_at": updated_at,
        }


# シングルトンインスタンス
_notion_task_service: Optional[NotionTaskService] = None


def get_notion_task_service() -> NotionTaskService:
    """NotionTaskServiceのシングルトンインスタンスを取得"""
    global _notion_task_service
    if _notion_task_service is None:
        _notion_task_service = NotionTaskService()
    return _notion_task_service
