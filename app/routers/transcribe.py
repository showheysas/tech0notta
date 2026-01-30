from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.job import Job, JobStatus
from app.services.blob_storage import get_blob_storage_service
from app.services.azure_speech_batch import get_azure_speech_batch_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["transcribe"])


class TranscribeRequest(BaseModel):
    job_id: str


@router.post("/transcribe")
async def transcribe_audio(
    request: TranscribeRequest,
    db: Session = Depends(get_db)
):
    try:
        job = db.query(Job).filter(Job.job_id == request.job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status != JobStatus.UPLOADED.value:
            raise HTTPException(
                status_code=400,
                detail=f"Job is not in UPLOADED status. Current status: {job.status}"
            )

        job.status = JobStatus.TRANSCRIBING.value
        job.error_message = None
        db.commit()

        blob_sas_url = get_blob_storage_service().get_blob_sas_url(job.blob_name)
        transcription_id = get_azure_speech_batch_service().submit_transcription(
            blob_sas_url
        )

        job.transcription_job_id = transcription_id
        db.commit()
        db.refresh(job)

        return {
            "job_id": job.job_id,
            "status": job.status,
            "transcription_job_id": job.transcription_job_id,
            "message": "Transcription started"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        if 'job' in locals():
            job.status = JobStatus.FAILED.value
            job.error_message = str(e)
            db.commit()
        raise HTTPException(status_code=500, detail="Failed to transcribe audio")


@router.get("/transcribe/status")
async def transcribe_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        if job.status == JobStatus.TRANSCRIBED.value:
            return {
                "job_id": job.job_id,
                "status": job.status,
                "transcription": job.transcription,
            }

        if job.status == JobStatus.FAILED.value:
            return {
                "job_id": job.job_id,
                "status": job.status,
                "error_message": job.error_message,
            }

        if job.status != JobStatus.TRANSCRIBING.value:
            return {"job_id": job.job_id, "status": job.status}

        if not job.transcription_job_id:
            raise HTTPException(status_code=500, detail="Missing transcription job ID")

        batch_status = get_azure_speech_batch_service().get_transcription_status(
            job.transcription_job_id
        )

        if batch_status.get("status") == "Succeeded":
            transcription = get_azure_speech_batch_service().fetch_transcription_text(
                job.transcription_job_id
            )
            job.transcription = transcription
            job.status = JobStatus.TRANSCRIBED.value
            db.commit()
            db.refresh(job)
            return {
                "job_id": job.job_id,
                "status": job.status,
                "transcription": job.transcription,
            }

        if batch_status.get("status") == "Failed":
            job.status = JobStatus.FAILED.value
            job.error_message = str(batch_status.get("error"))
            db.commit()
            return {
                "job_id": job.job_id,
                "status": job.status,
                "error_message": job.error_message,
            }

        return {
            "job_id": job.job_id,
            "status": job.status,
            "batch_status": batch_status.get("status"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking transcription status: {e}")
        raise HTTPException(status_code=500, detail="Failed to check transcription status")
