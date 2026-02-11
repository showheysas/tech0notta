from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.job import Job, JobStatus
from app.services.azure_openai import get_azure_openai_service
import logging
from datetime import datetime, date
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["summarize"])


class SummarizeRequest(BaseModel):
    job_id: str
    template_prompt: str | None = None
    auto_extract_metadata: bool = True  # MVP新機能: 自動でメタデータ抽出を実行


async def extract_metadata_background(job_id: str, db: Session):
    """バックグラウンドでメタデータとタスクを抽出"""
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job or not job.summary:
            return
        
        # ステータスを更新
        job.status = JobStatus.EXTRACTING_METADATA.value
        job.updated_at = datetime.utcnow()
        db.commit()
        
        # メタデータ抽出
        from app.services.metadata_service import get_metadata_service
        metadata_service = get_metadata_service()
        
        default_date = job.created_at.date() if job.created_at else date.today()
        metadata = await metadata_service.extract_metadata(
            summary=job.summary,
            transcription=job.transcription,
            default_date=default_date
        )
        
        # タスク抽出
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
        
        # 抽出結果をJSONとして保存
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
        job.updated_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"Metadata and tasks extracted for job {job_id} in background")
        
    except Exception as e:
        logger.error(f"Error extracting metadata in background for job {job_id}: {e}")
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                # エラーでもSUMMARIZEDに戻す（手動でメタデータ抽出を再実行可能）
                job.status = JobStatus.SUMMARIZED.value
                job.error_message = f"メタデータ抽出エラー: {str(e)}"
                job.updated_at = datetime.utcnow()
                db.commit()
        except:
            pass


@router.post("/summarize")
async def summarize_transcription(
    request: SummarizeRequest,
    background_tasks: BackgroundTasks,
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

        summary = get_azure_openai_service().generate_summary(
            job.transcription,
            template_prompt=request.template_prompt
        )

        job.summary = summary
        job.status = JobStatus.SUMMARIZED.value
        job.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(job)
        
        # MVP新機能: 自動でメタデータ抽出を実行
        if request.auto_extract_metadata:
            background_tasks.add_task(extract_metadata_background, job.job_id, db)
            return {
                "job_id": job.job_id,
                "status": job.status,
                "summary": job.summary,
                "message": "要約が完了しました。メタデータ抽出をバックグラウンドで実行中です。"
            }

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
