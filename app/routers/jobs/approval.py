"""Jobs 承認フローエンドポイント"""
import json
import logging
import traceback
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.job import Job, JobStatus
from app.models.user import User
from app.timezone import jst_now

from .schemas import JobApproveRequest, JobApproveResponse

logger = logging.getLogger(__name__)

router = APIRouter()


async def process_approval_background(
    job_id: str,
    request: JobApproveRequest
):
    """
    議事録承認後のバックグラウンド処理
    - Notion議事録DB投入
    - タスク登録
    - Slack通知送信
    """
    from app.database import SessionLocal
    db = SessionLocal()

    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found in background task: {job_id}")
            return

        tasks_registered = 0
        notifications_sent = 0

        # 1. Notion議事録DBに投入
        try:
            from app.services.notion_client import get_notion_client
            notion_client = get_notion_client()

            metadata_dict = {}
            if job.job_metadata:
                try:
                    metadata_dict = json.loads(job.job_metadata)
                    logger.info(f"Parsed metadata for job {job_id}: {metadata_dict}")
                except (json.JSONDecodeError, TypeError) as je:
                    logger.error(f"Failed to parse metadata for job {job_id}: {je}", exc_info=True)
                    logger.error(f"Metadata type: {type(job.job_metadata)}, value: {job.job_metadata}")
                    metadata_dict = {}
            else:
                logger.warning(f"No metadata found for job {job_id}")

            logger.info(f"Creating Notion page for job {job_id} with metadata: {metadata_dict}")

            notion_result = await notion_client.create_meeting_record(
                title=metadata_dict.get("mtg_name") or job.filename,
                summary=job.summary or "",
                metadata=metadata_dict
            )

            if notion_result:
                job.notion_page_id = notion_result.get("id")
                job.notion_page_url = notion_result.get("url")
                db.commit()
                logger.info(f"Created Notion page for job {job_id}: {job.notion_page_url}")

                if request.project_id and job.notion_page_id:
                    try:
                        await notion_client.update_meeting_project_relation(
                            meeting_page_id=job.notion_page_id,
                            project_page_id=request.project_id
                        )
                        logger.info(f"Set project relation for job {job_id}: {request.project_id}")
                    except Exception as e:
                        logger.error(f"Failed to set project relation for job {job_id}: {e}")
            else:
                logger.error(f"Notion client returned None for job {job_id}")

        except Exception as e:
            logger.error(f"Failed to create Notion page for job {job_id}: {e}", exc_info=True)
            logger.error(f"Traceback: {traceback.format_exc()}")

        # 2. タスクをNotion タスクDBに登録
        if not request.register_tasks:
            logger.info(f"Task registration skipped (register_tasks=False) for job {job_id}")
        elif not job.extracted_tasks:
            logger.warning(f"Task registration skipped (no extracted_tasks) for job {job_id}")

        if request.register_tasks and job.extracted_tasks:
            try:
                tasks_list = json.loads(job.extracted_tasks)
                logger.info(f"Attempting to register {len(tasks_list)} tasks for job {job_id}")

                from app.services.task_service import get_task_service
                from app.models.task import TaskRegisterRequest, TaskToRegister, TaskPriority

                task_service = get_task_service()

                tasks_to_register = []
                for task_data in tasks_list:
                    due_date_str = task_data.get("due_date")
                    due_date = None
                    if due_date_str:
                        try:
                            due_date = date.fromisoformat(due_date_str)
                        except ValueError:
                            logger.warning(f"Invalid due_date format: {due_date_str}, using default")
                            due_date = date.today() + timedelta(days=7)
                    else:
                        due_date = date.today() + timedelta(days=7)

                    priority_str = task_data.get("priority", "中")
                    priority = TaskPriority.MEDIUM
                    if priority_str == "高":
                        priority = TaskPriority.HIGH
                    elif priority_str == "低":
                        priority = TaskPriority.LOW

                    task_to_register = TaskToRegister(
                        title=task_data.get("title", ""),
                        description=task_data.get("description"),
                        assignee=task_data.get("assignee", "未割り当て"),
                        due_date=due_date,
                        priority=priority,
                        subtasks=[]
                    )
                    tasks_to_register.append(task_to_register)
                    logger.info(f"Task to register: {task_to_register.title} - {task_to_register.assignee} - {task_to_register.due_date}")

                if tasks_to_register:
                    register_request = TaskRegisterRequest(
                        job_id=job_id,
                        project_id=request.project_id,
                        meeting_page_id=job.notion_page_id,
                        tasks=tasks_to_register
                    )

                    logger.info(f"Calling task_service.register_tasks with {len(tasks_to_register)} tasks")
                    register_response = await task_service.register_tasks(register_request)
                    tasks_registered = register_response.registered_count
                    logger.info(f"Successfully registered {tasks_registered} tasks for job {job_id}")

                    if job.notion_page_id and register_response.task_ids:
                        try:
                            from app.services.notion_client import get_notion_client
                            notion_client = get_notion_client()
                            await notion_client.update_meeting_tasks_relation(
                                meeting_page_id=job.notion_page_id,
                                task_ids=register_response.task_ids
                            )
                            logger.info(f"Updated meeting tasks relation for job {job_id} with {len(register_response.task_ids)} tasks")
                        except Exception as e:
                            logger.error(f"Failed to update meeting tasks relation: {e}")
                else:
                    logger.warning(f"No tasks to register for job {job_id}")

            except Exception as e:
                logger.error(f"Failed to register tasks for job {job_id}: {type(e).__name__}: {e}", exc_info=True)
                logger.error(f"Task registration traceback: {traceback.format_exc()}")

        # 3. Slack通知送信
        if request.send_notifications:
            try:
                from app.services.slack_service import get_slack_service
                slack_service = get_slack_service()

                await slack_service.send_meeting_approved_notification(
                    job_id=job_id,
                    filename=job.filename,
                    summary=job.summary[:500] if job.summary else "",
                    notion_url=job.notion_page_url
                )
                notifications_sent += 1

                # タスク割り当て通知（TODO: 担当者ごとに送信）

                logger.info(f"Sent {notifications_sent} notifications for job {job_id}")

            except Exception as e:
                logger.error(f"Failed to send notifications for job {job_id}: {e}")

        # ステータスを完了に更新
        job.status = JobStatus.COMPLETED.value
        job.updated_at = jst_now()
        if tasks_registered == 0 and request.register_tasks and job.extracted_tasks:
            job.error_message = f"WARNING: タスク登録0件（extracted_tasks有り、register_tasks=True）"
        else:
            job.error_message = None
        db.commit()

        logger.info(f"Approval processing completed for job {job_id}: {tasks_registered} tasks, {notifications_sent} notifications")

    except Exception as e:
        logger.error(f"Error in approval processing for job {job_id}: {e}")
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = str(e)
                job.updated_at = jst_now()
                db.commit()
        except Exception as rollback_err:
            logger.error(f"Failed to update job status after error for job {job_id}: {rollback_err}", exc_info=True)
    finally:
        db.close()


@router.post("/{job_id}/approve", response_model=JobApproveResponse)
async def approve_job(
    job_id: str,
    request: JobApproveRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    議事録を承認する

    Requirements: F-11, F-12, F-13, F-16, F-17, F-18
    """
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in [JobStatus.REVIEWING.value, JobStatus.SUMMARIZED.value]:
        raise HTTPException(
            status_code=400,
            detail=f"現在のステータス({job.status})では承認できません。確認・修正画面で内容を確認してください。"
        )

    job.status = JobStatus.CREATING_NOTION.value
    job.updated_at = jst_now()
    db.commit()

    if not request.project_id and job.job_metadata:
        try:
            metadata_dict = json.loads(job.job_metadata)
            if metadata_dict.get("project_id"):
                request.project_id = metadata_dict["project_id"]
        except (json.JSONDecodeError, TypeError):
            pass

    background_tasks.add_task(process_approval_background, job_id, request)

    return JobApproveResponse(
        job_id=job.job_id,
        status="processing",
        message="議事録を承認しました。Notion投入とタスク登録をバックグラウンドで実行中です。"
    )
