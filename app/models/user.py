from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.database import Base


class User(Base):
    __tablename__ = "users"

    azure_user_id = Column(String(36), primary_key=True, index=True, nullable=False)
    email = Column(String(255), nullable=True)
    notion_user_page_id = Column(String(36), nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<User(azure_user_id={self.azure_user_id}, is_admin={self.is_admin})>"
