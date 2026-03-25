"""Jobs リスト・詳細・統計・更新エンドポイント"""
import json
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_authorized_project_ids
from app.database import get_db
from app.models.job import Job, JobStatus
from app.models.user import User
from app.timezone import jst_now

from .schemas import (
    JobCustomerUpdate,
    JobResponse,
    JobStatsResponse,
    JobUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats", response_model=JobStatsResponse)
def get_job_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ダッシュボード用統計情報を取得"""
    total_meetings = db.query(func.count(Job.id)).scalar() or 0

    pending_approval = db.query(func.count(Job.id)).filter(
        Job.status.in_([JobStatus.SUMMARIZED.value, JobStatus.EXTRACTING_METADATA.value])
    ).scalar() or 0

    reviewing = db.query(func.count(Job.id)).filter(
        Job.status == JobStatus.REVIEWING.value
    ).scalar() or 0

    synced_notion = db.query(func.count(Job.id)).filter(
        Job.status == JobStatus.COMPLETED.value
    ).scalar() or 0

    return JobStatsResponse(
        total_meetings=total_meetings,
        pending_approval=pending_approval,
        synced_notion=synced_notion,
        reviewing=reviewing
    )


@router.get("/", response_model=list[JobResponse])
def list_jobs(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    authorized_ids: Optional[set[str]] = Depends(get_authorized_project_ids),
    db: Session = Depends(get_db),
):
    """
    ジョブ一覧を取得 (作成日時降順)
    管理者は全件、一般ユーザーは所属案件のジョブのみ。
    """
    query = db.query(Job)

    if status:
        query = query.filter(Job.status == status)

    jobs = query.order_by(Job.created_at.desc()).offset(skip).limit(limit).all()

    from app.services.transcription_service import check_and_update_transcription_status

    for job in jobs:
        if job.status == JobStatus.TRANSCRIBING.value:
            try:
                check_and_update_transcription_status(job, db)
            except Exception as e:
                logger.warning(f"Failed to auto-update status for job {job.job_id}: {e}")

    result = [JobResponse.from_job(job) for job in jobs]

    if authorized_ids is not None:
        result = [
            j for j in result
            if j.metadata and j.metadata.project_id and j.metadata.project_id in authorized_ids
        ]

    return result


@router.put("/{job_id}/customer")
def update_job_customer(
    job_id: str,
    data: JobCustomerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """議事録の顧客紐付けを更新する"""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not hasattr(job, 'customer_id'):
        pass

    # TODO: Notionリレーション設定
    return {
        "job_id": job.job_id,
        "customer_id": data.customer_id,
        "message": "顧客紐付けを更新しました"
    }


@router.put("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: str,
    data: JobUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """議事録の内容を更新する"""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.REVIEWING.value, JobStatus.SUMMARIZED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"現在のステータス({job.status})では更新できません。"
        )

    if data.summary is not None:
        job.summary = data.summary

    if data.metadata is not None:
        metadata_dict = data.metadata.model_dump()
        job.job_metadata = json.dumps(metadata_dict, ensure_ascii=False)

        if data.metadata.meeting_date:
            try:
                job.meeting_date = date.fromisoformat(data.metadata.meeting_date)
            except ValueError:
                pass

    if data.extracted_tasks is not None:
        tasks_list = [t.model_dump() for t in data.extracted_tasks]
        job.extracted_tasks = json.dumps(tasks_list, ensure_ascii=False)

    job.updated_at = jst_now()
    db.commit()
    db.refresh(job)

    logger.info(f"Job {job_id} updated")

    return JobResponse.from_job(job)


# 注意: このエンドポイントは必ず /stats や他の固定パスエンドポイントの後に定義する
# そうしないと job_id として "stats" がマッチしてしまう
@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """特定ジョブの詳細を取得"""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_job(job)
