from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.models.deal import DealCreate, DealUpdate, DealResponse, DealStatus
from app.services.crm_service import get_crm_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/deals", tags=["deals"])


@router.post("", response_model=DealResponse)
async def create_deal(data: DealCreate):
    """
    商談を作成する

    必須フィールド: customer_id, name
    """
    if not data.customer_id or not data.customer_id.strip():
        raise HTTPException(status_code=400, detail="顧客IDは必須です")
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="商談名は必須です")

    service = get_crm_service()
    return await service.create_deal(data)


@router.get("", response_model=List[DealResponse])
async def list_deals(
    customer_id: Optional[str] = Query(None, description="顧客IDでフィルター"),
    status: Optional[DealStatus] = Query(None, description="ステータスでフィルター"),
):
    """
    商談一覧を取得する（フィルター対応）
    """
    service = get_crm_service()
    return await service.get_deals(customer_id=customer_id, status=status)


@router.get("/{deal_id}", response_model=DealResponse)
async def get_deal(deal_id: str):
    """
    商談詳細を取得する
    """
    service = get_crm_service()
    return await service.get_deal(deal_id)


@router.put("/{deal_id}", response_model=DealResponse)
async def update_deal(deal_id: str, data: DealUpdate):
    """
    商談を更新する

    ステータスが「成約」または「失注」に変更された場合、close_dateが自動設定されます。
    """
    service = get_crm_service()
    return await service.update_deal(deal_id, data)


@router.delete("/{deal_id}")
async def delete_deal(deal_id: str):
    """
    商談を削除する
    """
    service = get_crm_service()
    await service.delete_deal(deal_id)
    return {"message": "商談を削除しました"}
