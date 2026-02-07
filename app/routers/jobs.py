from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.job import Job, JobStatus
from pydantic import BaseModel

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
