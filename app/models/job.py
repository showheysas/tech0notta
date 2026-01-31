from sqlalchemy import Column, String, Integer, DateTime, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from app.database import Base


class JobStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    SUMMARIZING = "summarizing"
    SUMMARIZED = "summarized"
    CREATING_NOTION = "creating_notion"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(36), unique=True, index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    blob_name = Column(String(512), nullable=True)
    blob_url = Column(String(512), nullable=True)
    status = Column(String(50), default=JobStatus.PENDING.value, nullable=False)
    transcription = Column(Text, nullable=True)
    transcription_job_id = Column(String(128), nullable=True)
    summary = Column(Text, nullable=True)
    notion_page_id = Column(String(255), nullable=True)
    notion_page_url = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    duration = Column(Integer, nullable=True)  # 秒単位
    last_viewed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Job(job_id={self.job_id}, status={self.status})>"
