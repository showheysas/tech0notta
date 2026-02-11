"""
タスクサービス - タスク抽出・分解・登録・管理のビジネスロジック

Azure OpenAIによるタスク抽出・分解、Notion Task DBとの連携を担当します。
"""
from typing import List, Optional
from datetime import date, timedelta
from app.models.task import (
    TaskExtractRequest,
    TaskExtractResponse,
    ExtractedTask,
    TaskDecomposeRequest,
    TaskDecomposeResponse,
    TaskRegisterRequest,
    TaskRegisterResponse,
    TaskUpdate,
    TaskResponse,
    TaskStatus,
    TaskPriority,
)
from app.services.azure_openai import get_azure_openai_service
from fastapi import HTTPException
import logging
import json

logger = logging.getLogger(__name__)


class TaskService:
    """タスク管理サービス"""

    async def extract_tasks(self, request: TaskExtractRequest) -> TaskExtractResponse:
        """
        議事録からタスクを自動抽出する

        Azure OpenAIを使用して議事録の要約からアクションアイテムを抽出します。
        担当者が未指定の場合は「未割り当て」、期限が未指定の場合は会議日+7日を設定します。

        Args:
            request: タスク抽出リクエスト

        Returns:
            抽出されたタスクのリスト

        Raises:
            HTTPException: AI処理エラー
        """
        try:
            logger.info(f"Extracting tasks from job_id: {request.job_id}")
            
            # Azure OpenAIサービスを取得
            openai_service = get_azure_openai_service()
            
            # タスク抽出用のプロンプトを設計
            system_prompt = """あなたはプロジェクト管理の専門家です。
議事録の要約からアクションアイテム（タスク）を抽出してください。

以下のJSON形式で出力してください:
{
  "tasks": [
    {
      "title": "タスクのタイトル（簡潔に）",
      "description": "タスクの詳細説明（任意）",
      "assignee": "担当者名（明示されている場合のみ）",
      "due_date": "期限（YYYY-MM-DD形式、明示されている場合のみ）",
      "is_abstract": true/false（「資料作成」「調査」など抽象的なタスクの場合はtrue）
    }
  ]
}

ルール:
1. 明確なアクションアイテムのみを抽出してください
2. 担当者が明示されていない場合は、assigneeフィールドを省略してください
3. 期限が明示されていない場合は、due_dateフィールドを省略してください
4. タスクが抽象的で具体的なステップに分解が必要な場合は、is_abstractをtrueにしてください
5. タスクが見つからない場合は、空の配列を返してください
6. 必ずJSON形式で出力してください"""

            user_prompt = f"""会議日: {request.meeting_date}

議事録要約:
{request.summary}

上記の議事録からアクションアイテムを抽出してください。"""

            # Azure OpenAI APIを呼び出し
            response = openai_service.client.chat.completions.create(
                model=openai_service.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            # レスポンスをパース
            content = response.choices[0].message.content
            logger.info(f"OpenAI response: {content}")
            
            result = json.loads(content)
            tasks_data = result.get("tasks", [])
            
            # デフォルト値を適用
            extracted_tasks = []
            for task_data in tasks_data:
                # 担当者のデフォルト値: 未割り当て
                assignee = task_data.get("assignee")
                if not assignee or not assignee.strip():
                    assignee = "未割り当て"
                
                # 期限のデフォルト値: 会議日 + 7日
                due_date_str = task_data.get("due_date")
                if due_date_str:
                    try:
                        due_date = date.fromisoformat(due_date_str)
                    except ValueError:
                        logger.warning(f"Invalid due_date format: {due_date_str}, using default")
                        due_date = request.meeting_date + timedelta(days=7)
                else:
                    due_date = request.meeting_date + timedelta(days=7)
                
                extracted_task = ExtractedTask(
                    title=task_data.get("title", ""),
                    description=task_data.get("description"),
                    assignee=assignee,
                    due_date=due_date,
                    is_abstract=task_data.get("is_abstract", False)
                )
                extracted_tasks.append(extracted_task)
            
            logger.info(f"Extracted {len(extracted_tasks)} tasks")
            
            return TaskExtractResponse(
                job_id=request.job_id,
                tasks=extracted_tasks
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            raise HTTPException(
                status_code=500,
                detail="タスク抽出に失敗しました。AI応答の形式が不正です。"
            )
        except Exception as e:
            logger.error(f"Error extracting tasks: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"タスク抽出に失敗しました: {str(e)}"
            )

    async def decompose_task(
        self, request: TaskDecomposeRequest
    ) -> TaskDecomposeResponse:
        """
        抽象的なタスクを具体的なサブタスクに分解する

        Azure OpenAIを使用して3-5個の具体的なステップに分解します。
        サブタスクの期限は親タスクの期限以前に設定されます。

        Args:
            request: タスク分解リクエスト

        Returns:
            分解されたサブタスクのリスト

        Raises:
            HTTPException: AI処理エラー
        """
        try:
            logger.info(f"Decomposing task: {request.task_title}")
            
            # Azure OpenAIサービスを取得
            openai_service = get_azure_openai_service()
            
            # タスク分解用のプロンプトを設計
            system_prompt = """あなたはプロジェクト管理の専門家です。
抽象的なタスクを具体的な実行ステップに分解してください。

以下のJSON形式で出力してください:
{
  "subtasks": [
    {
      "title": "サブタスクのタイトル（具体的なアクション）",
      "description": "サブタスクの詳細説明（任意）",
      "order": 1
    },
    {
      "title": "サブタスクのタイトル",
      "description": "サブタスクの詳細説明（任意）",
      "order": 2
    }
  ]
}

ルール:
1. サブタスクは3個から5個の範囲で生成してください
2. サブタスクは論理的な実行順序に従って並べてください
3. orderは1から始まる連番を設定してください
4. 各サブタスクは具体的で実行可能なアクションにしてください
5. 必ずJSON形式で出力してください"""

            # タスク説明を含むユーザープロンプトを作成
            description_text = f"\n詳細: {request.task_description}" if request.task_description else ""
            user_prompt = f"""タスク: {request.task_title}{description_text}
期限: {request.parent_due_date}

上記のタスクを3-5個の具体的なサブタスクに分解してください。"""

            # Azure OpenAI APIを呼び出し
            response = openai_service.client.chat.completions.create(
                model=openai_service.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            # レスポンスをパース
            content = response.choices[0].message.content
            logger.info(f"OpenAI response: {content}")
            
            result = json.loads(content)
            subtasks_data = result.get("subtasks", [])
            
            # サブタスク数の検証（3-5個）
            if len(subtasks_data) < 3:
                logger.warning(f"Generated only {len(subtasks_data)} subtasks, expected 3-5")
                raise HTTPException(
                    status_code=500,
                    detail="サブタスクの生成数が不足しています（最低3個必要）"
                )
            elif len(subtasks_data) > 5:
                logger.warning(f"Generated {len(subtasks_data)} subtasks, limiting to 5")
                subtasks_data = subtasks_data[:5]
            
            # サブタスクを作成
            from app.models.task import SubTaskItem
            subtasks = []
            for i, subtask_data in enumerate(subtasks_data, start=1):
                subtask = SubTaskItem(
                    title=subtask_data.get("title", ""),
                    description=subtask_data.get("description"),
                    order=i  # 順序を保証するため、インデックスベースで設定
                )
                subtasks.append(subtask)
            
            logger.info(f"Decomposed into {len(subtasks)} subtasks")
            
            return TaskDecomposeResponse(
                parent_task=request.task_title,
                subtasks=subtasks
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            raise HTTPException(
                status_code=500,
                detail="タスク分解に失敗しました。AI応答の形式が不正です。"
            )
        except HTTPException:
            # 既にHTTPExceptionの場合はそのまま再送出
            raise
        except Exception as e:
            logger.error(f"Error decomposing task: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"タスク分解に失敗しました: {str(e)}"
            )

    async def register_tasks(
        self, request: TaskRegisterRequest
    ) -> TaskRegisterResponse:
        """
        承認されたタスクをNotion Task DBに登録する

        親タスク・サブタスクの作成、リレーション設定を行います。
        Notion APIエラー時は3回リトライ（指数バックオフ）します。

        Args:
            request: タスク登録リクエスト

        Returns:
            登録結果

        Raises:
            HTTPException: Notion APIエラー（リトライ後も失敗した場合）
        """
        try:
            logger.info(f"Registering {len(request.tasks)} tasks for job_id: {request.job_id}")
            
            # Notion クライアントを取得
            from app.services.notion_task_service import get_notion_task_service
            notion_service = get_notion_task_service()
            
            # 議事録のページIDを取得
            meeting_page_id = None
            if hasattr(request, 'meeting_page_id') and request.meeting_page_id:
                meeting_page_id = request.meeting_page_id
            
            task_ids = []
            
            # 各タスクを登録
            for task in request.tasks:
                try:
                    # 親タスクを登録
                    parent_task_id = await notion_service.create_task(
                        title=task.title,
                        description=task.description,
                        assignee=task.assignee,
                        due_date=task.due_date,
                        priority=task.priority,
                        status=TaskStatus.NOT_STARTED,
                        project_id=request.project_id,
                        meeting_page_id=meeting_page_id,
                        parent_task_id=None
                    )
                    
                    task_ids.append(parent_task_id)
                    logger.info(f"Created parent task: {parent_task_id} - {task.title}")
                    
                    # サブタスクがある場合は登録
                    if task.subtasks:
                        for subtask in task.subtasks:
                            # サブタスクの期限は親タスクの期限以前に設定
                            subtask_id = await notion_service.create_task(
                                title=subtask.title,
                                description=subtask.description,
                                assignee=task.assignee,  # 親タスクの担当者を継承
                                due_date=task.due_date,  # 親タスクの期限を使用
                                priority=task.priority,  # 親タスクの優先度を継承
                                status=TaskStatus.NOT_STARTED,
                                project_id=request.project_id,
                                meeting_page_id=meeting_page_id,
                                parent_task_id=parent_task_id
                            )
                            
                            task_ids.append(subtask_id)
                            logger.info(f"Created subtask: {subtask_id} - {subtask.title}")
                    
                except Exception as e:
                    logger.error(f"Failed to register task '{task.title}': {e}")
                    # 個別のタスク登録エラーは記録するが、処理は継続
                    continue
            
            logger.info(f"Successfully registered {len(task_ids)} tasks/subtasks")
            
            return TaskRegisterResponse(
                job_id=request.job_id,
                registered_count=len(task_ids),
                task_ids=task_ids
            )
            
        except Exception as e:
            logger.error(f"Error registering tasks: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"タスク登録に失敗しました: {str(e)}"
            )

    async def get_tasks(
        self,
        project_id: Optional[str] = None,
        assignee: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        priority: Optional[TaskPriority] = None,
        due_date_from: Optional[date] = None,
        due_date_to: Optional[date] = None,
        sort_by: str = "due_date",
        sort_order: str = "asc",
    ) -> List[TaskResponse]:
        """
        タスク一覧を取得する（フィルター・ソート対応）

        Args:
            project_id: プロジェクトIDでフィルター
            assignee: 担当者でフィルター
            status: ステータスでフィルター
            priority: 優先度でフィルター
            due_date_from: 期限開始日でフィルター
            due_date_to: 期限終了日でフィルター
            sort_by: ソートキー（due_date, priority, assignee, created_at）
            sort_order: ソート順（asc, desc）

        Returns:
            タスクレスポンスのリスト

        Raises:
            HTTPException: Notion APIエラー
        """
        try:
            logger.info(f"Getting tasks with filters: project_id={project_id}, assignee={assignee}, status={status}")
            
            # Notion Task DBからタスクを取得
            from app.services.notion_task_service import get_notion_task_service
            notion_service = get_notion_task_service()
            
            notion_tasks = await notion_service.query_tasks(
                project_id=project_id,
                assignee=assignee,
                status=status,
                priority=priority,
                due_date_from=due_date_from,
                due_date_to=due_date_to,
            )
            
            # NotionレスポンスをパースしてTaskResponseに変換
            tasks = []
            for notion_task in notion_tasks:
                parsed = notion_service.parse_task_response(notion_task)
                
                # サブタスク数を計算（親タスクIDが一致するタスクを検索）
                # Note: 効率化のため、ここでは0に設定。必要に応じて別途クエリを実行
                subtask_count = 0
                completed_subtask_count = 0
                
                # 期限超過判定
                is_overdue = False
                if parsed["due_date"] and parsed["status"] != TaskStatus.COMPLETED:
                    is_overdue = parsed["due_date"] < date.today()
                
                task_response = TaskResponse(
                    id=parsed["id"],
                    title=parsed["title"],
                    description=None,  # Notionのページコンテンツから取得する必要がある
                    assignee=parsed["assignee"],
                    due_date=parsed["due_date"],
                    status=parsed["status"],
                    priority=parsed["priority"],
                    project_id=parsed["project_id"],
                    project_name=None,  # プロジェクト名は別途取得が必要
                    meeting_id=parsed["meeting_id"],
                    parent_task_id=parsed["parent_task_id"],
                    subtask_count=subtask_count,
                    completed_subtask_count=completed_subtask_count,
                    is_overdue=is_overdue,
                    completion_date=parsed["completion_date"],
                    notion_page_url=parsed["notion_page_url"],
                    created_at=parsed["created_at"],
                    updated_at=parsed["updated_at"],
                )
                tasks.append(task_response)
            
            # ソート処理
            reverse = (sort_order == "desc")
            
            if sort_by == "due_date":
                tasks.sort(key=lambda t: t.due_date if t.due_date else date.max, reverse=reverse)
            elif sort_by == "priority":
                # 優先度: 高 > 中 > 低
                priority_order = {TaskPriority.HIGH: 3, TaskPriority.MEDIUM: 2, TaskPriority.LOW: 1}
                tasks.sort(key=lambda t: priority_order.get(t.priority, 0), reverse=reverse)
            elif sort_by == "assignee":
                tasks.sort(key=lambda t: t.assignee or "", reverse=reverse)
            elif sort_by == "created_at":
                tasks.sort(key=lambda t: t.created_at, reverse=reverse)
            
            logger.info(f"Retrieved {len(tasks)} tasks")
            return tasks
            
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"タスク一覧の取得に失敗しました: {str(e)}"
            )

    async def get_task(self, task_id: str) -> TaskResponse:
        """
        タスク詳細を取得する

        Args:
            task_id: タスクID

        Returns:
            タスクレスポンス

        Raises:
            HTTPException: タスクが見つからない場合
        """
        try:
            logger.info(f"Getting task: {task_id}")
            
            # Notion Task DBからタスクを取得
            from app.services.notion_task_service import get_notion_task_service
            notion_service = get_notion_task_service()
            
            notion_task = await notion_service.get_task(task_id)
            parsed = notion_service.parse_task_response(notion_task)
            
            # サブタスク数を計算
            subtask_count = 0
            completed_subtask_count = 0
            
            # 期限超過判定
            is_overdue = False
            if parsed["due_date"] and parsed["status"] != TaskStatus.COMPLETED:
                is_overdue = parsed["due_date"] < date.today()
            
            task_response = TaskResponse(
                id=parsed["id"],
                title=parsed["title"],
                description=None,
                assignee=parsed["assignee"],
                due_date=parsed["due_date"],
                status=parsed["status"],
                priority=parsed["priority"],
                project_id=parsed["project_id"],
                project_name=None,
                meeting_id=parsed["meeting_id"],
                parent_task_id=parsed["parent_task_id"],
                subtask_count=subtask_count,
                completed_subtask_count=completed_subtask_count,
                is_overdue=is_overdue,
                completion_date=parsed["completion_date"],
                notion_page_url=parsed["notion_page_url"],
                created_at=parsed["created_at"],
                updated_at=parsed["updated_at"],
            )
            
            logger.info(f"Retrieved task: {task_id}")
            return task_response
            
        except Exception as e:
            logger.error(f"Error getting task {task_id}: {e}")
            if "404" in str(e) or "not found" in str(e).lower():
                raise HTTPException(
                    status_code=404,
                    detail="タスクが見つかりません"
                )
            raise HTTPException(
                status_code=500,
                detail=f"タスクの取得に失敗しました: {str(e)}"
            )

    async def update_task(self, task_id: str, data: TaskUpdate) -> TaskResponse:
        """
        タスクを更新する

        ステータスが「完了」に変更された場合、completion_dateを自動設定します。

        Args:
            task_id: タスクID
            data: 更新データ

        Returns:
            更新されたタスクレスポンス

        Raises:
            HTTPException: タスクが見つからない場合、バリデーションエラー
        """
        try:
            logger.info(f"Updating task: {task_id}")
            
            # バリデーション: titleとdue_dateは必須（更新時に指定された場合）
            if data.title is not None and not data.title.strip():
                raise HTTPException(
                    status_code=400,
                    detail="タスク名は必須です"
                )
            
            # 完了日の自動設定
            completion_date = None
            if data.status == TaskStatus.COMPLETED:
                completion_date = date.today()
            
            # Notion Task DBを更新
            from app.services.notion_task_service import get_notion_task_service
            notion_service = get_notion_task_service()
            
            await notion_service.update_task(
                task_id=task_id,
                title=data.title,
                assignee=data.assignee,
                due_date=data.due_date,
                status=data.status,
                priority=data.priority,
                completion_date=completion_date,
            )
            
            # 更新後のタスクを取得して返す
            updated_task = await self.get_task(task_id)
            
            logger.info(f"Updated task: {task_id}")
            return updated_task
            
        except HTTPException:
            # 既にHTTPExceptionの場合はそのまま再送出
            raise
        except Exception as e:
            logger.error(f"Error updating task {task_id}: {e}")
            if "404" in str(e) or "not found" in str(e).lower():
                raise HTTPException(
                    status_code=404,
                    detail="タスクが見つかりません"
                )
            raise HTTPException(
                status_code=500,
                detail=f"タスクの更新に失敗しました: {str(e)}"
            )

    async def delete_task(self, task_id: str) -> None:
        """
        タスクを削除する

        Args:
            task_id: タスクID

        Raises:
            HTTPException: タスクが見つからない場合
        """
        try:
            logger.info(f"Deleting task: {task_id}")
            
            # Notion Task DBから削除（アーカイブ）
            from app.services.notion_task_service import get_notion_task_service
            notion_service = get_notion_task_service()
            
            await notion_service.delete_task(task_id)
            
            logger.info(f"Deleted task: {task_id}")
            
        except Exception as e:
            logger.error(f"Error deleting task {task_id}: {e}")
            if "404" in str(e) or "not found" in str(e).lower():
                raise HTTPException(
                    status_code=404,
                    detail="タスクが見つかりません"
                )
            raise HTTPException(
                status_code=500,
                detail=f"タスクの削除に失敗しました: {str(e)}"
            )


# シングルトンインスタンス
_task_service: Optional[TaskService] = None


def get_task_service() -> TaskService:
    """TaskServiceのシングルトンインスタンスを取得"""
    global _task_service
    if _task_service is None:
        _task_service = TaskService()
    return _task_service
