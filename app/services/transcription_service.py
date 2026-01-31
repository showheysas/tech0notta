from sqlalchemy.orm import Session
from app.models.job import Job, JobStatus
from app.services.azure_speech_batch import get_azure_speech_batch_service
import logging

logger = logging.getLogger(__name__)

def check_and_update_transcription_status(job: Job, db: Session) -> Job:
    """
    ジョブの文字起こしステータスを確認し、必要であればDBを更新する。
    
    Args:
        job: 更新対象のJobモデルインスタンス
        db: データベースセッション
        
    Returns:
        更新されたJobモデルインスタンス
    """
    if job.status != JobStatus.TRANSCRIBING.value:
        return job

    if not job.transcription_job_id:
        # トランスクリプションIDがない場合はエラーステータスにはぜず、ログを出力して現状維持（またはエラー扱いにするか検討）
        logger.warning(f"Job {job.job_id} is in TRANSCRIBING status but has no transcription_job_id")
        return job

    try:
        batch_status = get_azure_speech_batch_service().get_transcription_status(
            job.transcription_job_id
        )
        
        status_text = batch_status.get("status")

        if status_text == "Succeeded":
            transcription = get_azure_speech_batch_service().fetch_transcription_text(
                job.transcription_job_id
            )
            job.transcription = transcription
            job.status = JobStatus.TRANSCRIBED.value
            db.commit()
            db.refresh(job)
            logger.info(f"Job {job.job_id} transcription succeeded and updated.")

        elif status_text == "Failed":
            job.status = JobStatus.FAILED.value
            job.error_message = str(batch_status.get("error"))
            db.commit()
            db.refresh(job)
            logger.error(f"Job {job.job_id} transcription failed: {job.error_message}")
            
    except Exception as e:
        logger.error(f"Error updating transcription status for job {job.job_id}: {e}")
        # ここでは例外を再送せず、ログ出力にとどめて処理を継続させる
        
    return job
