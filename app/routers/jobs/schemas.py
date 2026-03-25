"""Jobs ルーター用 Pydantic スキーマ"""
import json
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel


class MetadataResponse(BaseModel):
    """メタデータレスポンス"""
    mtg_name: Optional[str] = None
    participants: list[str] = []
    company_name: Optional[str] = None
    meeting_date: Optional[str] = None
    meeting_type: Optional[str] = None
    project: Optional[str] = None
    project_id: Optional[str] = None
    key_stakeholders: list[str] = []
    key_team: Optional[str] = None
    search_keywords: Optional[str] = None
    is_knowledge: bool = False
    materials_url: Optional[str] = None
    notes: Optional[str] = None
    related_meetings: list[str] = []


class ExtractedTaskResponse(BaseModel):
    """抽出されたタスクレスポンス"""
    title: str
    description: Optional[str] = None
    assignee: str = "未割り当て"
    due_date: Optional[str] = None
    priority: str = "中"
    is_abstract: bool = False


class JobResponse(BaseModel):
    id: int
    job_id: str
    filename: str
    file_size: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    notion_page_url: Optional[str] = None
    duration: Optional[int] = None
    last_viewed_at: Optional[datetime] = None
    transcription: Optional[str] = None
    summary: Optional[str] = None
    metadata: Optional[MetadataResponse] = None
    extracted_tasks: Optional[list[ExtractedTaskResponse]] = None
    meeting_date: Optional[date] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_job(cls, job) -> "JobResponse":
        """JobモデルからJobResponseを生成"""
        metadata = None
        if job.job_metadata:
            try:
                metadata_dict = json.loads(job.job_metadata)
                metadata = MetadataResponse(**metadata_dict)
            except (json.JSONDecodeError, TypeError):
                pass

        extracted_tasks = None
        if job.extracted_tasks:
            try:
                tasks_list = json.loads(job.extracted_tasks)
                extracted_tasks = [ExtractedTaskResponse(**t) for t in tasks_list]
            except (json.JSONDecodeError, TypeError):
                pass

        return cls(
            id=job.id,
            job_id=job.job_id,
            filename=job.filename,
            file_size=job.file_size,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            notion_page_url=job.notion_page_url,
            duration=job.duration,
            last_viewed_at=job.last_viewed_at,
            transcription=job.transcription,
            summary=job.summary,
            metadata=metadata,
            extracted_tasks=extracted_tasks,
            meeting_date=job.meeting_date
        )


class JobStatsResponse(BaseModel):
    total_meetings: int
    pending_approval: int
    synced_notion: int
    reviewing: int = 0


class JobCustomerUpdate(BaseModel):
    customer_id: Optional[str] = None


class ExtractMetadataResponse(BaseModel):
    """メタデータ抽出レスポンス"""
    job_id: str
    status: str
    metadata: MetadataResponse
    extracted_tasks: list[ExtractedTaskResponse]
    message: str


class JobUpdateRequest(BaseModel):
    """Job更新リクエスト"""
    summary: Optional[str] = None
    metadata: Optional[MetadataResponse] = None
    extracted_tasks: Optional[list[ExtractedTaskResponse]] = None


class JobApproveRequest(BaseModel):
    """議事録承認リクエスト"""
    register_tasks: bool = True
    send_notifications: bool = True
    project_id: Optional[str] = None


class JobApproveResponse(BaseModel):
    """議事録承認レスポンス"""
    job_id: str
    status: str
    notion_page_url: Optional[str] = None
    tasks_registered: int = 0
    notifications_sent: int = 0
    message: str
