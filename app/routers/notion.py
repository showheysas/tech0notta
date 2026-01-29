from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.job import Job, JobStatus
from app.services.notion_client import get_notion_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["notion"])


class NotionCreateRequest(BaseModel):
    job_id: str
    title: str = None


@router.post("/notion/create")
async def create_notion_page(
    request: NotionCreateRequest,
    db: Session = Depends(get_db)
):
    try:
        job = db.query(Job).filter(Job.job_id == request.job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status != JobStatus.SUMMARIZED.value:
            raise HTTPException(
                status_code=400,
                detail=f"Job is not in SUMMARIZED status. Current status: {job.status}"
            )

        if not job.transcription or not job.summary:
            raise HTTPException(
                status_code=400,
                detail="Missing transcription or summary"
            )

        job.status = JobStatus.CREATING_NOTION.value
        db.commit()

        title = request.title or f"議事録 - {job.filename}"

        page_id, page_url = get_notion_service().create_meeting_note(
            title=title,
            transcription=job.transcription,
            summary=job.summary,
            audio_filename=job.filename
        )

        job.notion_page_id = page_id
        job.notion_page_url = page_url
        job.status = JobStatus.COMPLETED.value
        db.commit()
        db.refresh(job)

        return {
            "job_id": job.job_id,
            "status": job.status,
            "notion_page_id": job.notion_page_id,
            "notion_page_url": job.notion_page_url,
            "message": "Notion page created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating Notion page: {e}")
        if 'job' in locals():
            job.status = JobStatus.FAILED.value
            job.error_message = str(e)
            db.commit()
        raise HTTPException(status_code=500, detail="Failed to create Notion page")


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "job_id": job.job_id,
            "filename": job.filename,
            "file_size": job.file_size,
            "status": job.status,
            "blob_url": job.blob_url,
            "transcription": job.transcription,
            "summary": job.summary,
            "notion_page_id": job.notion_page_id,
            "notion_page_url": job.notion_page_url,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get job status")
