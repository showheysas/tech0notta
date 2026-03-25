"""Jobs メタデータ抽出エンドポイント"""
import json
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.job import Job, JobStatus
from app.models.user import User
from app.timezone import jst_now

from .schemas import (
    ExtractedTaskResponse,
    ExtractMetadataResponse,
    MetadataResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{job_id}/extract-metadata", response_model=ExtractMetadataResponse)
async def extract_metadata(
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    議事録からメタデータとタスクを自動抽出する

    Requirements: F-04, F-14
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.summary:
        raise HTTPException(
            status_code=400,
            detail="要約が完了していません。先に要約を生成してください。"
        )

    try:
        job.status = JobStatus.EXTRACTING_METADATA.value
        job.updated_at = jst_now()
        db.commit()

        from app.services.metadata_service import get_metadata_service
        metadata_service = get_metadata_service()

        default_date = job.created_at.date() if job.created_at else date.today()
        metadata = await metadata_service.extract_metadata(
            summary=job.summary,
            transcription=job.transcription,
            default_date=default_date
        )

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
        job.updated_at = jst_now()
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
        job.updated_at = jst_now()
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"メタデータ抽出に失敗しました: {str(e)}"
        )
