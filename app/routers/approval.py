from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models.job import Job, JobStatus
from app.services.slack_service import get_slack_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["approval"])


class ApprovalRequest(BaseModel):
    """承認リクエスト"""
    job_id: str
    approved_by: str
    comment: str = ""


class ApprovalResponse(BaseModel):
    """承認レスポンス"""
    job_id: str
    status: str
    message: str
    slack_posted: bool


@router.post("/approve", response_model=ApprovalResponse)
async def approve_minutes(
    request: ApprovalRequest,
    db: Session = Depends(get_db)
):
    """
    議事録を承認してSlackに通知
    
    Args:
        request: 承認リクエスト（job_id）
        db: データベースセッション
        
    Returns:
        承認結果とSlack投稿状況
    """
    try:
        # Jobを取得
        job = db.query(Job).filter(Job.job_id == request.job_id).first()
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # 要約が生成されているか確認
        if not job.summary:
            raise HTTPException(
                status_code=400,
                detail="Summary not generated yet"
            )
        
        # ステータスを更新
        job.status = JobStatus.COMPLETED.value
        db.commit()
        db.refresh(job)
        
        # Slackに通知
        slack_service = get_slack_service()
        try:
            slack_response = slack_service.post_approved_minutes(
                job,
                approved_by=request.approved_by,
                comment=request.comment
            )
            slack_posted = slack_response.get("ok", False)
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
            slack_posted = False
        
        return ApprovalResponse(
            job_id=job.job_id,
            status=job.status,
            message="Minutes approved successfully",
            slack_posted=slack_posted
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving minutes: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve minutes")
