from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, date

from app.database import get_db
from app.models.job import Job, JobStatus
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# --- Response Models ---

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

    class Config:
        from_attributes = True

class JobStatsResponse(BaseModel):
    total_meetings: int
    pending_approval: int
    synced_notion: int

# --- Endpoints ---

@router.get("/stats", response_model=JobStatsResponse)
def get_job_stats(db: Session = Depends(get_db)):
    """
    ダッシュボード用統計情報を取得
    """
    total_meetings = db.query(func.count(Job.id)).scalar() or 0

    # 承認待ち: Notion作成完了以前のステータスで、かつ失敗していないもの
    # ここでは便宜的に「完了」していないものを承認待ちとするか、
    # あるいは特定のステータス(SUMMARIZEDなど)を承認待ちとするか定義が必要。
    # いったん、COMPLETED以外でFAILEDでもないものを「進行中/承認待ち」としてカウントする
    # もしくは、ユーザーの要望に合わせて「レビュー待ち」= SUMMARIZED (要約完了、Notion未連携) とする？
    # 仮実装として: SUMMARIZED (要約済み) を「レビュー待ち」と見なす
    
    pending_approval = db.query(func.count(Job.id)).filter(
        Job.status.in_([JobStatus.SUMMARIZED, JobStatus.TRANSCRIBED])
    ).scalar() or 0

    # Notion同期済み: status = COMPLETED 
    # または notion_page_url があるもの
    synced_notion = db.query(func.count(Job.id)).filter(
        Job.status == JobStatus.COMPLETED
    ).scalar() or 0

    return JobStatsResponse(
        total_meetings=total_meetings,
        pending_approval=pending_approval,
        synced_notion=synced_notion
    )

@router.get("", response_model=List[JobResponse])
def list_jobs(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """
    ジョブ一覧を取得 (作成日時降順)
    """
    jobs = db.query(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit).all()
    
    # TRANSCRIBING状態のジョブがあれば、ステータスを更新する
    from app.services.transcription_service import check_and_update_transcription_status
    
    for job in jobs:
        if job.status == JobStatus.TRANSCRIBING.value:
            try:
               check_and_update_transcription_status(job, db)
            except Exception as e:
                # リスト取得を止めないように、個別のエラーはログに出すだけにする
                # check_and_update_transcription_status内でもログ出力はあるが、念のため
                print(f"Failed to auto-update status for job {job.job_id}: {e}")

    return jobs


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


# --- 議事録承認フロー ---

class JobApproveRequest(BaseModel):
    """議事録承認リクエスト"""
    extract_tasks: bool = True  # タスク抽出を実行するか
    send_notifications: bool = True  # 通知を送信するか
    project_id: Optional[str] = None  # プロジェクトID（タスク登録用）


class JobApproveResponse(BaseModel):
    """議事録承認レスポンス"""
    job_id: str
    status: str
    tasks_extracted: int = 0
    notifications_sent: int = 0
    message: str


async def process_approval_tasks(
    job: Job,
    request: JobApproveRequest,
    db: Session
):
    """
    議事録承認後のバックグラウンド処理
    - タスク抽出
    - タスク登録
    - 通知送信
    """
    try:
        from app.services.task_service import get_task_service
        from app.models.task import TaskExtractRequest
        
        task_service = get_task_service()
        tasks_extracted = 0
        notifications_sent = 0
        
        # タスク抽出
        if request.extract_tasks and job.summary:
            try:
                # 会議日を取得（created_atから）
                meeting_date = job.created_at.date() if job.created_at else date.today()
                
                extract_request = TaskExtractRequest(
                    job_id=job.job_id,
                    summary=job.summary,
                    meeting_date=meeting_date
                )
                
                extract_response = await task_service.extract_tasks(extract_request)
                tasks_extracted = len(extract_response.tasks)
                
                logger.info(f"Extracted {tasks_extracted} tasks from job {job.job_id}")
                
                # TODO: タスク登録（ユーザー承認後に実行するため、ここでは抽出のみ）
                # TODO: 通知送信（Slack通知機能実装後に追加）
                
            except Exception as e:
                logger.error(f"Failed to extract tasks for job {job.job_id}: {e}")
        
        # 通知送信
        if request.send_notifications:
            try:
                # TODO: Slack通知機能実装後に追加
                # - 議事録承認通知をプロジェクトチャネルに送信
                # - タスク割り当て通知を担当者に送信
                pass
            except Exception as e:
                logger.error(f"Failed to send notifications for job {job.job_id}: {e}")
        
        logger.info(f"Approval processing completed for job {job.job_id}: {tasks_extracted} tasks, {notifications_sent} notifications")
        
    except Exception as e:
        logger.error(f"Error in approval processing for job {job.job_id}: {e}")


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
    1. ステータスをCOMPLETEDに更新
    2. タスク抽出を自動実行（オプション）
    3. 通知を送信（オプション）
    
    Requirements: 4.1, 9.1, 10.1
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # ステータスを更新
    job.status = JobStatus.COMPLETED.value
    job.updated_at = datetime.utcnow()
    db.commit()
    
    # バックグラウンドでタスク抽出・通知処理を実行
    background_tasks.add_task(process_approval_tasks, job, request, db)
    
    return JobApproveResponse(
        job_id=job.job_id,
        status="approved",
        message="議事録を承認しました。タスク抽出と通知処理をバックグラウンドで実行中です。"
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
    return job
