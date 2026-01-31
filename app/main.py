from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers import upload, transcribe, summarize, notion
from app.routers import zoom_webhook, bot_router, sync_router, jobs, live_router, rtms_router
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
app.include_router(zoom_webhook.router)
app.include_router(bot_router.router)
app.include_router(sync_router.router)
app.include_router(live_router.router)
app.include_router(rtms_router.router)


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
            "job_status": "GET /api/jobs/{job_id}"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
