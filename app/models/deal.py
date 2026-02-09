from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from enum import Enum


class DealStatus(str, Enum):
    """商談ステータス"""
    LEAD = "リード"
    IN_PROGRESS = "商談中"
    PROPOSED = "提案済み"
    NEGOTIATING = "交渉中"
    WON = "成約"
    LOST = "失注"


class DealCreate(BaseModel):
    """商談作成リクエスト"""
    customer_id: str
    name: str
    amount: Optional[int] = None
    probability: Optional[int] = None  # 0-100
    expected_close_date: Optional[date] = None
    status: DealStatus = DealStatus.LEAD


class DealUpdate(BaseModel):
    """商談更新リクエスト"""
    name: Optional[str] = None
    amount: Optional[int] = None
    probability: Optional[int] = None
    expected_close_date: Optional[date] = None
    status: Optional[DealStatus] = None


class DealResponse(BaseModel):
    """商談レスポンス"""
    id: str
    customer_id: str
    name: str
    amount: Optional[int] = None
    probability: Optional[int] = None
    expected_close_date: Optional[date] = None
    status: DealStatus
    close_date: Optional[date] = None
    notion_page_url: str = ""
    created_at: datetime
    updated_at: datetime
