from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job, JobStatus
from app.services.blob_storage import get_blob_storage_service
from app.config import settings
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload")
async def upload_audio(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        if file.size > settings.max_file_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB"
            )

        allowed_formats = ["audio/wav", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/ogg"]
        if file.content_type not in allowed_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file format. Allowed formats: {', '.join(allowed_formats)}"
            )

        job_id = str(uuid.uuid4())

        job = Job(
            job_id=job_id,
            filename=file.filename,
            file_size=file.size,
            status=JobStatus.UPLOADING.value
        )
        db.add(job)
        db.commit()

        file_data = await file.read()
        blob_name, blob_url = get_blob_storage_service().upload_file(
            file_data=file_data,
            filename=file.filename,
            content_type=file.content_type
        )

        job.blob_name = blob_name
        job.blob_url = blob_url
        job.status = JobStatus.UPLOADED.value
        db.commit()
        db.refresh(job)

        return {
            "job_id": job.job_id,
            "filename": job.filename,
            "status": job.status,
            "blob_url": job.blob_url,
            "message": "File uploaded successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        if 'job' in locals():
            job.status = JobStatus.FAILED.value
            job.error_message = str(e)
            db.commit()
        raise HTTPException(status_code=500, detail="Failed to upload file")
