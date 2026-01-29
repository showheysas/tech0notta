from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.job import Job, JobStatus
from app.services.azure_openai import get_azure_openai_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["summarize"])


class SummarizeRequest(BaseModel):
    job_id: str


@router.post("/summarize")
async def summarize_transcription(
    request: SummarizeRequest,
    db: Session = Depends(get_db)
):
    try:
        job = db.query(Job).filter(Job.job_id == request.job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status != JobStatus.TRANSCRIBED.value:
            raise HTTPException(
                status_code=400,
                detail=f"Job is not in TRANSCRIBED status. Current status: {job.status}"
            )

        if not job.transcription:
            raise HTTPException(status_code=400, detail="No transcription available")

        job.status = JobStatus.SUMMARIZING.value
        db.commit()

        summary = get_azure_openai_service().generate_summary(job.transcription)

        job.summary = summary
        job.status = JobStatus.SUMMARIZED.value
        db.commit()
        db.refresh(job)

        return {
            "job_id": job.job_id,
            "status": job.status,
            "summary": job.summary,
            "message": "Summary generated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        if 'job' in locals():
            job.status = JobStatus.FAILED.value
            job.error_message = str(e)
            db.commit()
        raise HTTPException(status_code=500, detail="Failed to generate summary")
