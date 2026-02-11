from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.job import Job, JobStatus
from app.services.slack_service import get_slack_service
from app.services.notion_client import get_notion_service
from app.services.task_service import get_task_service
from app.models.task import TaskRegisterRequest, TaskToRegister, TaskPriority
from datetime import date, timedelta
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["approval"])


class ApprovalRequest(BaseModel):
    """承認リクエスト"""
    job_id: str
    approved_by: str = "システム"
    comment: str = ""
    # メタデータ（確認・修正後）
    mtg_name: str = ""
    participants: list = []
    company_name: str = ""
    meeting_date: str = ""
    meeting_type: str = "定例"
    project_name: str = ""
    key_stakeholders: list = []
    key_team: str = ""
    search_keywords: str = ""
    # タスク情報
    tasks: list = []


class ApprovalResponse(BaseModel):
    """承認レスポンス"""
    job_id: str
    status: str
    message: str
    notion_page_url: str = ""
    slack_posted: bool
    tasks_registered: int = 0


@router.post("/approve", response_model=ApprovalResponse)
async def approve_minutes(
    request: ApprovalRequest,
    db: Session = Depends(get_db)
):
    """
    議事録を承認してNotionに保存、タスクを登録、Slackに通知
    
    Args:
        request: 承認リクエスト（job_id、メタデータ、タスク情報）
        db: データベースセッション
        
    Returns:
        承認結果、Notion URL、タスク登録数、Slack投稿状況
    """
    try:
        # Jobを取得
        job = db.query(Job).filter(Job.job_id == request.job_id).first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # 要約が生成されているか確認
        if not job.summary:
            raise HTTPException(
                status_code=400,
                detail="Summary not generated yet"
            )
        
        # 1. 議事録をNotionに保存
        notion_service = get_notion_service()
        notion_page_url = ""
        
        try:
            # メタデータを構築
            metadata = {
                "mtg_name": request.mtg_name or job.filename,
                "participants": request.participants,
                "company_name": request.company_name,
                "meeting_date": request.meeting_date or date.today().isoformat(),
                "meeting_type": request.meeting_type,
                "project_name": request.project_name,
                "key_stakeholders": request.key_stakeholders,
                "key_team": request.key_team,
                "search_keywords": request.search_keywords,
                "is_knowledge": False,
            }
            
            # Notion議事録DBに保存
            notion_result = await notion_service.create_meeting_record(
                title=request.mtg_name or job.filename,
                summary=job.summary,
                metadata=metadata
            )
            
            if notion_result:
                notion_page_url = notion_result["url"]
                # JobにNotion URLを保存
                job.notion_page_url = notion_page_url
                
                logger.info(f"Meeting record saved to Notion: {notion_result['id']}")
                
                # 2. タスクをNotion Task DBに登録
                tasks_registered = 0
                if request.tasks:
                    try:
                        task_service = get_task_service()
                        
                        # タスクデータを変換
                        tasks_to_register = []
                        for task_data in request.tasks:
                            # 期限の設定（指定されていない場合は会議日+7日）
                            due_date_str = task_data.get("due_date")
                            if due_date_str:
                                try:
                                    due_date = date.fromisoformat(due_date_str)
                                except ValueError:
                                    due_date = date.fromisoformat(request.meeting_date) + timedelta(days=7)
                            else:
                                due_date = date.fromisoformat(request.meeting_date) + timedelta(days=7)
                            
                            # 優先度の設定
                            priority_str = task_data.get("priority", "中")
                            try:
                                priority = TaskPriority(priority_str)
                            except ValueError:
                                priority = TaskPriority.MEDIUM
                            
                            task_to_register = TaskToRegister(
                                title=task_data.get("title", ""),
                                description=task_data.get("description"),
                                assignee=task_data.get("assignee", "未割り当て"),
                                due_date=due_date,
                                priority=priority,
                                subtasks=task_data.get("subtasks", [])
                            )
                            tasks_to_register.append(task_to_register)
                        
                        # タスク登録リクエストを作成
                        register_request = TaskRegisterRequest(
                            job_id=job.job_id,
                            project_id=None,  # プロジェクトIDは今後実装
                            meeting_page_id=notion_result["id"],  # 議事録のNotion Page ID
                            tasks=tasks_to_register
                        )
                        
                        # タスクを登録
                        register_response = await task_service.register_tasks(register_request)
                        tasks_registered = register_response.registered_count
                        
                        logger.info(f"Registered {tasks_registered} tasks for job {job.job_id}")
                        
                    except Exception as e:
                        logger.error(f"Task registration failed: {e}")
                        # タスク登録失敗は警告として記録するが、承認処理は継続
                        
        except Exception as e:
            logger.error(f"Notion save failed: {e}")
            # Notion保存失敗は警告として記録するが、承認処理は継続
        
        # 3. ステータスを更新
        job.status = JobStatus.COMPLETED.value
        db.commit()
        db.refresh(job)
        
        # 4. Slackに通知
        slack_service = get_slack_service()
        try:
            slack_response = slack_service.post_approved_minutes(
                job,
                approved_by=request.approved_by,
                comment=request.comment
            )
            slack_posted = slack_response.get("ok", False)
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
            slack_posted = False
        
        return ApprovalResponse(
            job_id=job.job_id,
            status=job.status,
            message="Minutes approved and saved to Notion successfully",
            notion_page_url=notion_page_url,
            slack_posted=slack_posted,
            tasks_registered=tasks_registered
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving minutes: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve minutes")
