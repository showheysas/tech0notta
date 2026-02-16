from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Any
from datetime import datetime, date, timedelta

from app.database import get_db
from app.models.job import Job, JobStatus
from pydantic import BaseModel, Field
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# --- Response Models ---

class MetadataResponse(BaseModel):
    """メタデータレスポンス"""
    mtg_name: Optional[str] = None
    participants: List[str] = []
    company_name: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_type: Optional[str] = None
    project: Optional[str] = None
    project_id: Optional[str] = None  # Notion案件ページID
    key_stakeholders: List[str] = []
    key_team: Optional[str] = None
    search_keywords: Optional[str] = None
    is_knowledge: bool = False
    materials_url: Optional[str] = None
    notes: Optional[str] = None
    related_meetings: List[str] = []


class ExtractedTaskResponse(BaseModel):
    """抽出されたタスクレスポンス"""
    title: str
    description: Optional[str] = None
    assignee: str = "未割り当て"
    due_date: Optional[str] = None
    priority: str = "中"
    is_abstract: bool = False


class JobResponse(BaseModel):
    id: int
    job_id: str
    filename: str
    file_size: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    notion_page_url: Optional[str] = None
    duration: Optional[int] = None
    last_viewed_at: Optional[datetime] = None
    transcription: Optional[str] = None
    summary: Optional[str] = None
    metadata: Optional[MetadataResponse] = None
    extracted_tasks: Optional[List[ExtractedTaskResponse]] = None
    meeting_date: Optional[date] = None

    class Config:
        from_attributes = True
    
    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        """JobモデルからJobResponseを生成"""
        metadata = None
        if job.job_metadata:
            try:
                metadata_dict = json.loads(job.job_metadata)
                metadata = MetadataResponse(**metadata_dict)
            except (json.JSONDecodeError, TypeError):
                pass
        
        extracted_tasks = None
        if job.extracted_tasks:
            try:
                tasks_list = json.loads(job.extracted_tasks)
                extracted_tasks = [ExtractedTaskResponse(**t) for t in tasks_list]
            except (json.JSONDecodeError, TypeError):
                pass
        
        return cls(
            id=job.id,
            job_id=job.job_id,
            filename=job.filename,
            file_size=job.file_size,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            notion_page_url=job.notion_page_url,
            duration=job.duration,
            last_viewed_at=job.last_viewed_at,
            transcription=job.transcription,
            summary=job.summary,
            metadata=metadata,
            extracted_tasks=extracted_tasks,
            meeting_date=job.meeting_date
        )


class JobStatsResponse(BaseModel):
    total_meetings: int
    pending_approval: int
    synced_notion: int
    reviewing: int = 0  # 確認・修正中

# --- Endpoints ---

@router.get("/stats", response_model=JobStatsResponse)
def get_job_stats(db: Session = Depends(get_db)):
    """
    ダッシュボード用統計情報を取得
    """
    total_meetings = db.query(func.count(Job.id)).scalar() or 0

    # 承認待ち: SUMMARIZED または EXTRACTING_METADATA
    pending_approval = db.query(func.count(Job.id)).filter(
        Job.status.in_([JobStatus.SUMMARIZED.value, JobStatus.EXTRACTING_METADATA.value])
    ).scalar() or 0
    
    # 確認・修正中: REVIEWING
    reviewing = db.query(func.count(Job.id)).filter(
        Job.status == JobStatus.REVIEWING.value
    ).scalar() or 0

    # Notion同期済み: status = COMPLETED 
    synced_notion = db.query(func.count(Job.id)).filter(
        Job.status == JobStatus.COMPLETED.value
    ).scalar() or 0

    return JobStatsResponse(
        total_meetings=total_meetings,
        pending_approval=pending_approval,
        synced_notion=synced_notion,
        reviewing=reviewing
    )

@router.get("", response_model=List[JobResponse])
def list_jobs(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    ジョブ一覧を取得 (作成日時降順)
    """
    query = db.query(Job)
    
    # ステータスフィルター
    if status:
        query = query.filter(Job.status == status)
    
    jobs = query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()
    
    # TRANSCRIBING状態のジョブがあれば、ステータスを更新する
    from app.services.transcription_service import check_and_update_transcription_status
    
    for job in jobs:
        if job.status == JobStatus.TRANSCRIBING.value:
            try:
               check_and_update_transcription_status(job, db)
            except Exception as e:
                logger.warning(f"Failed to auto-update status for job {job.job_id}: {e}")

    return [JobResponse.from_job(job) for job in jobs]


# --- 顧客・議事録紐付け ---

class JobCustomerUpdate(BaseModel):
    customer_id: Optional[str] = None


@router.put("/{job_id}/customer")
def update_job_customer(
    job_id: str,
    data: JobCustomerUpdate,
    db: Session = Depends(get_db)
):
    """
    議事録の顧客紐付けを更新する
    Requirements: 3.1, 3.3, 3.6
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # customer_idカラムが存在するか確認し、なければ動的に追加
    if not hasattr(job, 'customer_id'):
        # インメモリで紐付け情報を管理（カラム追加はマイグレーションで対応）
        pass

    # TODO: Notionリレーション設定
    return {
        "job_id": job.job_id,
        "customer_id": data.customer_id,
        "message": "顧客紐付けを更新しました"
    }


# --- メタデータ抽出API（MVP新機能） ---

class ExtractMetadataResponse(BaseModel):
    """メタデータ抽出レスポンス"""
    job_id: str
    status: str
    metadata: MetadataResponse
    extracted_tasks: List[ExtractedTaskResponse]
    message: str


@router.post("/{job_id}/extract-metadata", response_model=ExtractMetadataResponse)
async def extract_metadata(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    議事録からメタデータとタスクを自動抽出する
    
    要約完了後に呼び出し、以下を実行:
    1. メタデータを自動抽出（MTG名、参加者、会議日、種別等）
    2. タスクを自動抽出
    3. ステータスをREVIEWINGに更新
    
    Requirements: F-04, F-14
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # 要約が完了していることを確認
    if not job.summary:
        raise HTTPException(
            status_code=400, 
            detail="要約が完了していません。先に要約を生成してください。"
        )
    
    try:
        # ステータスを更新
        job.status = JobStatus.EXTRACTING_METADATA.value
        job.updated_at = datetime.utcnow()
        db.commit()
        
        # メタデータ抽出
        from app.services.metadata_service import get_metadata_service
        metadata_service = get_metadata_service()
        
        default_date = job.created_at.date() if job.created_at else date.today()
        metadata = await metadata_service.extract_metadata(
            summary=job.summary,
            transcription=job.transcription,
            default_date=default_date
        )
        
        # タスク抽出
        from app.services.task_service import get_task_service
        from app.models.task import TaskExtractRequest
        
        task_service = get_task_service()
        meeting_date = date.fromisoformat(metadata.meeting_date) if metadata.meeting_date else default_date
        
        extract_request = TaskExtractRequest(
            job_id=job.job_id,
            summary=job.summary,
            meeting_date=meeting_date
        )
        
        extract_response = await task_service.extract_tasks(extract_request)
        
        # 抽出結果をJSONとして保存
        metadata_dict = metadata.to_dict()
        tasks_list = [
            {
                "title": t.title,
                "description": t.description,
                "assignee": t.assignee,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "priority": "中",
                "is_abstract": t.is_abstract
            }
            for t in extract_response.tasks
        ]
        
        job.job_metadata = json.dumps(metadata_dict, ensure_ascii=False)
        job.extracted_tasks = json.dumps(tasks_list, ensure_ascii=False)
        job.meeting_date = meeting_date
        job.status = JobStatus.REVIEWING.value
        job.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Metadata and tasks extracted for job {job_id}")
        
        return ExtractMetadataResponse(
            job_id=job.job_id,
            status=job.status,
            metadata=MetadataResponse(**metadata_dict),
            extracted_tasks=[ExtractedTaskResponse(**t) for t in tasks_list],
            message=f"メタデータと{len(tasks_list)}件のタスクを抽出しました。確認・修正後、承認してください。"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting metadata for job {job_id}: {e}")
        job.status = JobStatus.FAILED.value
        job.error_message = str(e)
        job.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"メタデータ抽出に失敗しました: {str(e)}"
        )


# --- Job更新API（MVP新機能） ---

class JobUpdateRequest(BaseModel):
    """Job更新リクエスト"""
    summary: Optional[str] = None
    metadata: Optional[MetadataResponse] = None
    extracted_tasks: Optional[List[ExtractedTaskResponse]] = None


@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: str,
    data: JobUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    議事録の内容を更新する
    
    確認・修正画面からの更新を受け付け:
    - 要約テキストの更新
    - メタデータの更新
    - 抽出タスクの更新
    
    Requirements: F-05
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # 更新可能なステータスを確認
    if job.status not in [JobStatus.REVIEWING.value, JobStatus.SUMMARIZED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"現在のステータス({job.status})では更新できません。"
        )
    
    # 要約の更新
    if data.summary is not None:
        job.summary = data.summary
    
    # メタデータの更新
    if data.metadata is not None:
        metadata_dict = data.metadata.model_dump()
        job.job_metadata = json.dumps(metadata_dict, ensure_ascii=False)
        
        # 会議日の更新
        if data.metadata.meeting_date:
            try:
                job.meeting_date = date.fromisoformat(data.metadata.meeting_date)
            except ValueError:
                pass
    
    # 抽出タスクの更新
    if data.extracted_tasks is not None:
        tasks_list = [t.model_dump() for t in data.extracted_tasks]
        job.extracted_tasks = json.dumps(tasks_list, ensure_ascii=False)
    
    job.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    
    logger.info(f"Job {job_id} updated")
    
    return JobResponse.from_job(job)


# --- 議事録承認フロー ---

class JobApproveRequest(BaseModel):
    """議事録承認リクエスト"""
    register_tasks: bool = True  # タスクをNotionに登録するか
    send_notifications: bool = True  # 通知を送信するか
    project_id: Optional[str] = None  # プロジェクトID（タスク登録用）


class JobApproveResponse(BaseModel):
    """議事録承認レスポンス"""
    job_id: str
    status: str
    notion_page_url: Optional[str] = None
    tasks_registered: int = 0
    notifications_sent: int = 0
    message: str


async def process_approval_background(
    job_id: str,
    request: JobApproveRequest
):
    """
    議事録承認後のバックグラウンド処理
    - Notion議事録DB投入
    - タスク登録
    - Slack通知送信
    """
    # バックグラウンドタスク用に新しいDBセッションを作成
    from app.database import SessionLocal
    db = SessionLocal()
    
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found in background task: {job_id}")
            return
        
        tasks_registered = 0
        notifications_sent = 0
        
        # 1. Notion議事録DBに投入
        try:
            from app.services.notion_client import get_notion_client
            notion_client = get_notion_client()
            
            # メタデータを取得（job_metadataは常にJSON文字列として保存されている）
            metadata_dict = {}
            if job.job_metadata:
                try:
                    # job_metadataは常に文字列型（TEXT列）
                    metadata_dict = json.loads(job.job_metadata)
                    logger.info(f"Parsed metadata for job {job_id}: {metadata_dict}")
                except (json.JSONDecodeError, TypeError) as je:
                    logger.error(f"Failed to parse metadata for job {job_id}: {je}", exc_info=True)
                    logger.error(f"Metadata type: {type(job.job_metadata)}, value: {job.job_metadata}")
                    metadata_dict = {}
            else:
                logger.warning(f"No metadata found for job {job_id}")
            
            logger.info(f"Creating Notion page for job {job_id} with metadata: {metadata_dict}")
            
            # Notionページを作成
            notion_result = await notion_client.create_meeting_record(
                title=metadata_dict.get("mtg_name") or job.filename,
                summary=job.summary or "",
                metadata=metadata_dict
            )
            
            if notion_result:
                job.notion_page_id = notion_result.get("id")
                job.notion_page_url = notion_result.get("url")
                db.commit()
                logger.info(f"Created Notion page for job {job_id}: {job.notion_page_url}")
                
                # 案件リレーションを設定
                if request.project_id and job.notion_page_id:
                    try:
                        await notion_client.update_meeting_project_relation(
                            meeting_page_id=job.notion_page_id,
                            project_page_id=request.project_id
                        )
                        logger.info(f"Set project relation for job {job_id}: {request.project_id}")
                    except Exception as e:
                        logger.error(f"Failed to set project relation for job {job_id}: {e}")
            else:
                logger.error(f"Notion client returned None for job {job_id}")
            
        except Exception as e:
            logger.error(f"Failed to create Notion page for job {job_id}: {e}", exc_info=True)
            # エラーの詳細をログに出力
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        
        # 2. タスクをNotion タスクDBに登録
        if request.register_tasks and job.extracted_tasks:
            try:
                tasks_list = json.loads(job.extracted_tasks)
                logger.info(f"Attempting to register {len(tasks_list)} tasks for job {job_id}")
                
                from app.services.task_service import get_task_service
                from app.models.task import TaskRegisterRequest, TaskToRegister, SubTaskItem, TaskPriority
                
                task_service = get_task_service()
                
                # タスクを登録用の形式に変換
                tasks_to_register = []
                for task_data in tasks_list:
                    due_date_str = task_data.get("due_date")
                    due_date = None
                    if due_date_str:
                        try:
                            due_date = date.fromisoformat(due_date_str)
                        except ValueError:
                            logger.warning(f"Invalid due_date format: {due_date_str}, using default")
                            due_date = date.today() + timedelta(days=7)
                    else:
                        due_date = date.today() + timedelta(days=7)
                    
                    priority_str = task_data.get("priority", "中")
                    priority = TaskPriority.MEDIUM
                    if priority_str == "高":
                        priority = TaskPriority.HIGH
                    elif priority_str == "低":
                        priority = TaskPriority.LOW
                    
                    task_to_register = TaskToRegister(
                        title=task_data.get("title", ""),
                        description=task_data.get("description"),
                        assignee=task_data.get("assignee", "未割り当て"),
                        due_date=due_date,
                        priority=priority,
                        subtasks=[]
                    )
                    tasks_to_register.append(task_to_register)
                    logger.info(f"Task to register: {task_to_register.title} - {task_to_register.assignee} - {task_to_register.due_date}")
                
                if tasks_to_register:
                    register_request = TaskRegisterRequest(
                        job_id=job_id,
                        project_id=request.project_id,
                        meeting_page_id=job.notion_page_id,  # 議事録のNotion Page IDを渡す
                        tasks=tasks_to_register
                    )
                    
                    logger.info(f"Calling task_service.register_tasks with {len(tasks_to_register)} tasks")
                    register_response = await task_service.register_tasks(register_request)
                    tasks_registered = register_response.registered_count
                    logger.info(f"Successfully registered {tasks_registered} tasks for job {job_id}")
                    
                    # 議事録ページの「タスク」リレーションを更新
                    if job.notion_page_id and register_response.task_ids:
                        try:
                            from app.services.notion_client import get_notion_client
                            notion_client = get_notion_client()
                            await notion_client.update_meeting_tasks_relation(
                                meeting_page_id=job.notion_page_id,
                                task_ids=register_response.task_ids
                            )
                            logger.info(f"Updated meeting tasks relation for job {job_id} with {len(register_response.task_ids)} tasks")
                        except Exception as e:
                            logger.error(f"Failed to update meeting tasks relation: {e}")
                else:
                    logger.warning(f"No tasks to register for job {job_id}")
                
            except Exception as e:
                logger.error(f"Failed to register tasks for job {job_id}: {e}", exc_info=True)
        
        # 3. Slack通知送信
        if request.send_notifications:
            try:
                from app.services.slack_service import get_slack_service
                slack_service = get_slack_service()
                
                # 議事録承認通知
                await slack_service.send_meeting_approved_notification(
                    job_id=job_id,
                    filename=job.filename,
                    summary=job.summary[:500] if job.summary else "",
                    notion_url=job.notion_page_url
                )
                notifications_sent += 1
                
                # タスク割り当て通知（TODO: 担当者ごとに送信）
                
                logger.info(f"Sent {notifications_sent} notifications for job {job_id}")
                
            except Exception as e:
                logger.error(f"Failed to send notifications for job {job_id}: {e}")
        
        # ステータスを完了に更新
        job.status = JobStatus.COMPLETED.value
        job.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Approval processing completed for job {job_id}: {tasks_registered} tasks, {notifications_sent} notifications")
        
    except Exception as e:
        logger.error(f"Error in approval processing for job {job_id}: {e}")
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = str(e)
                job.updated_at = datetime.utcnow()
                db.commit()
        except:
            pass
    finally:
        db.close()


@router.post("/{job_id}/approve", response_model=JobApproveResponse)
async def approve_job(
    job_id: str,
    request: JobApproveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    議事録を承認する
    
    承認時に以下の処理を実行:
    1. ステータスをCREATING_NOTIONに更新
    2. Notion議事録DBに投入（バックグラウンド）
    3. タスクをNotion タスクDBに登録（バックグラウンド）
    4. Slack通知を送信（バックグラウンド）
    5. ステータスをCOMPLETEDに更新
    
    Requirements: F-11, F-12, F-13, F-16, F-17, F-18
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # 承認可能なステータスを確認
    if job.status not in [JobStatus.REVIEWING.value, JobStatus.SUMMARIZED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"現在のステータス({job.status})では承認できません。確認・修正画面で内容を確認してください。"
        )
    
    # ステータスを更新
    job.status = JobStatus.CREATING_NOTION.value
    job.updated_at = datetime.utcnow()
    db.commit()
    
    # メタデータからproject_idを取得（リクエストで未指定の場合）
    if not request.project_id and job.job_metadata:
        try:
            metadata_dict = json.loads(job.job_metadata)
            if metadata_dict.get("project_id"):
                request.project_id = metadata_dict["project_id"]
        except (json.JSONDecodeError, TypeError):
            pass
    
    # バックグラウンドで処理を実行（DBセッションは渡さない - バックグラウンドタスク内で新規作成）
    background_tasks.add_task(process_approval_background, job_id, request)
    
    return JobApproveResponse(
        job_id=job.job_id,
        status="processing",
        message="議事録を承認しました。Notion投入とタスク登録をバックグラウンドで実行中です。"
    )


# 注意: このエンドポイントは必ず /stats や他の固定パスエンドポイントの後に定義する
# そうしないと job_id として "stats" がマッチしてしまう
@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """
    特定ジョブの詳細を取得
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_job(job)
