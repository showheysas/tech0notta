from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.job import Job, JobStatus
from app.services.blob_storage import get_blob_storage_service
from app.services.audio_extractor import get_audio_extractor
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

        # 許可されたファイル形式
        allowed_audio_formats = [
            "audio/wav", "audio/mpeg", "audio/mp3", "audio/mp4", 
            "audio/x-m4a", "audio/ogg", "audio/aac", "audio/flac"
        ]
        allowed_video_formats = [
            "video/mp4", "video/quicktime", "video/x-msvideo", 
            "video/webm", "video/x-matroska"
        ]
        allowed_formats = allowed_audio_formats + allowed_video_formats
        
        if file.content_type not in allowed_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file format. Allowed formats: audio (WAV, MP3, M4A, AAC, FLAC, OGG) or video (MP4, MOV, AVI, WebM, MKV)"
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

        # ファイルデータを読み込み
        file_data = await file.read()
        
        # 動画ファイルの場合は音声を抽出
        audio_extractor = get_audio_extractor()
        if audio_extractor.is_video_file(file.content_type):
            logger.info(f"Video file detected: {file.filename}. Extracting audio...")
            try:
                file_data, extracted_filename = audio_extractor.extract_audio(
                    file_data, 
                    file.filename
                )
                # 抽出された音声ファイル名を使用
                upload_filename = extracted_filename
                upload_content_type = "audio/wav"
                logger.info(f"Audio extracted successfully: {upload_filename}")
            except Exception as e:
                logger.error(f"Failed to extract audio: {e}")
                job.status = JobStatus.FAILED.value
                job.error_message = f"Failed to extract audio from video: {str(e)}"
                db.commit()
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to extract audio from video: {str(e)}"
                )
        else:
            upload_filename = file.filename
            upload_content_type = file.content_type
        
        # Blob Storageにアップロード
        blob_name, blob_url = get_blob_storage_service().upload_file(
            file_data=file_data,
            filename=upload_filename,
            content_type=upload_content_type
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
            "message": "File uploaded successfully" + (" (audio extracted from video)" if audio_extractor.is_video_file(file.content_type) else "")
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
