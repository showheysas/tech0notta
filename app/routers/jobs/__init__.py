"""
Jobs ルーターパッケージ

サブルーターを統合して、main.py からは従来通り
`from app.routers import jobs; app.include_router(jobs.router)` で利用可能。
"""
from fastapi import APIRouter

from .listing import router as listing_router
from .metadata import router as metadata_router
from .approval import router as approval_router
from .debug import router as debug_router

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# サブルーターを登録（順序が重要: /stats, /debug/* は /{job_id} より先に）
router.include_router(listing_router)
router.include_router(metadata_router)
router.include_router(approval_router)
router.include_router(debug_router)
