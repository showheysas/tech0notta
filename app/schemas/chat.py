from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional


class ChatSessionCreate(BaseModel):
    """チャットセッション作成リクエスト"""
    job_id: str = Field(..., description="議事録のJob ID")


class ChatSessionResponse(BaseModel):
    """チャットセッションレスポンス"""
    session_id: str
    job_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ChatMessageCreate(BaseModel):
    """チャットメッセージ作成リクエスト"""
    message: str = Field(..., min_length=1, max_length=2000, description="ユーザーのメッセージ")
    streaming: bool = Field(default=False, description="ストリーミングレスポンスを使用するか")


class ChatMessageResponse(BaseModel):
    """チャットメッセージレスポンス"""
    message_id: str
    role: str
    content: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChatHistoryResponse(BaseModel):
    """チャット履歴レスポンス"""
    session_id: str
    job_id: str
    messages: List[ChatMessageResponse]
    
    class Config:
        from_attributes = True


class ChatSessionListItem(BaseModel):
    """チャットセッション一覧の項目"""
    session_id: str
    job_id: str
    message_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ChatSessionListResponse(BaseModel):
    """チャットセッション一覧レスポンス"""
    sessions: List[ChatSessionListItem]
