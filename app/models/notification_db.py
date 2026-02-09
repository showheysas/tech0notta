"""
通知関連のSQLAlchemyモデル（PostgreSQL/SQLite内部DB用）

notifications: 通知履歴テーブル
reminder_history: リマインダー送信履歴テーブル
"""
from sqlalchemy import Column, String, Integer, DateTime, Date, Text, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class NotificationRecord(Base):
    """通知履歴テーブル"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), nullable=False)  # 'meeting_completed', 'task_assigned', 'reminder'
    job_id = Column(String(36), ForeignKey("jobs.job_id"), nullable=True)
    task_id = Column(String(255), nullable=True)  # Notion Task ID
    recipient_slack_id = Column(String(50), nullable=False)
    channel_id = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # 'pending', 'sent', 'failed'
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReminderHistory(Base):
    """リマインダー送信履歴テーブル"""
    __tablename__ = "reminder_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), nullable=False)  # Notion Task ID
    reminder_date = Column(Date, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('task_id', 'reminder_date', name='uq_task_reminder_date'),
    )
