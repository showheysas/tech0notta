from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import upload, transcribe, summarize, notion, chat, approval
from app.routers import zoom_webhook, bot_router, sync_router, jobs, live_router, rtms_router
from app.routers import customers, deals, tasks, notifications
from app.routers import projects as projects_router
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Meeting Notes API",
    description="API for transcribing audio and creating meeting notes in Notion",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注意: jobs.router は /api/jobs/stats パスを持つため、
# notion.router の /api/jobs/{job_id} より先に登録する必要がある
app.include_router(jobs.router)
app.include_router(upload.router)
app.include_router(transcribe.router)
app.include_router(summarize.router)
app.include_router(notion.router)
app.include_router(chat.router)
app.include_router(approval.router)
app.include_router(zoom_webhook.router)
app.include_router(bot_router.router)
app.include_router(sync_router.router)
app.include_router(live_router.router)
app.include_router(rtms_router.router)

# 新規機能ルーター（CRM、タスク管理、通知）
app.include_router(customers.router)
app.include_router(deals.router)
app.include_router(tasks.router)
app.include_router(notifications.router)
app.include_router(projects_router.router)


@app.on_event("startup")
async def startup_event():
    logger.info("Starting up Meeting Notes API")
    init_db()
    logger.info("Database initialized")


@app.get("/")
async def root():
    return {
        "message": "Meeting Notes API",
        "version": "1.0.0",
        "endpoints": {
            "upload": "POST /api/upload",
            "transcribe": "POST /api/transcribe",
            "transcribe_status": "GET /api/transcribe/status?job_id=...",
            "summarize": "POST /api/summarize",
            "notion_create": "POST /api/notion/create",
            "job_status": "GET /api/jobs/{job_id}",
            "chat_session_create": "POST /api/chat/sessions",
            "chat_message_send": "POST /api/chat/sessions/{session_id}/messages",
            "chat_history": "GET /api/chat/sessions/{session_id}/messages",
            "chat_sessions_list": "GET /api/chat/sessions",
            "approve": "POST /api/approve",
            "customers": "GET /api/customers",
            "customer_create": "POST /api/customers",
            "customer_detail": "GET /api/customers/{customer_id}",
            "deals": "GET /api/deals",
            "deal_create": "POST /api/deals",
            "deal_detail": "GET /api/deals/{deal_id}",
            "tasks": "GET /api/tasks",
            "task_extract": "POST /api/tasks/extract",
            "task_decompose": "POST /api/tasks/decompose",
            "task_register": "POST /api/tasks/register",
            "task_detail": "GET /api/tasks/{task_id}",
            "notification_meeting_approved": "POST /api/notifications/meeting-approved",
            "notification_task_assigned": "POST /api/notifications/task-assigned",
            "notification_reminder_batch": "GET /api/notifications/batch/reminder",
            "projects": "GET /api/projects",
            "project_create": "POST /api/projects"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
